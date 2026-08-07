from tree_sitter import Language, Parser
import tree_sitter_c
import re

from model.code_model import (
    FunctionInfo,
    ParameterInfo,
    StructInfo,
    EnumInfo,
    GlobalVariable,
    CFileInfo,
    FlowNode,
)


class ASTParser:
    """基于 tree-sitter 的 C 代码解析器。

    注意：tree-sitter 的 start_byte/end_byte 是字节偏移，因此所有
    源码切片都必须基于原始 bytes 数据（self._raw），切出后再 decode。
    若用 Python 字符串做切片，中文字符会导致偏移错位。
    """

    def __init__(self):
        self.parser = Parser()
        self.parser.language = Language(tree_sitter_c.language())
        self._raw = b""

    def parse(self, code):
        """code 为原始 bytes 或 str。"""
        if isinstance(code, str):
            code = code.encode("utf-8")
        self._raw = code
        result = CFileInfo()
        tree = self.parser.parse(code)
        self.walk(tree.root_node, result)
        return result

    # ---------- 通用辅助 ----------

    def _text(self, node):
        """按字节切片取节点源码文本。"""
        if node is None:
            return ""
        return self._raw[node.start_byte:node.end_byte].decode(
            "utf-8", errors="replace"
        )

    def _strip(self, node):
        return self._text(node).strip()

    def walk(self, node, result):
        if node.type == "function_definition":
            func = self.parse_function(node)
            if func.name:
                result.functions.append(func)
            # 不继续深入子节点（函数体内不会再有顶层声明）
            return
        elif node.type == "struct_specifier":
            s = self.parse_struct(node)
            if s:
                result.structs.append(s)
        elif node.type == "enum_specifier":
            e = self.parse_enum(node)
            if e:
                result.enums.append(e)
        elif node.type == "preproc_def":
            result.macros.append(self._strip(node))
        elif node.type == "preproc_include":
            result.includes.append(self._strip(node))
        elif node.type == "type_definition":
            result.typedefs.append(self._strip(node))
        elif node.type == "declaration":
            self.parse_global_declaration(node, result)

        for child in node.children:
            self.walk(child, result)

    # ---------- 全局变量 ----------

    def parse_global_declaration(self, node, result):
        """解析文件作用域的全局/静态变量声明。"""
        # 只处理文件顶层，不处理函数体内的 declaration（由 walk 通过
        # function_definition 提前 return 保证不会进入函数体）。
        text = self._strip(node)
        # 排除函数声明（形如 "xxx foo(int a);"）
        if self.find_node(node, "parameter_list") is not None:
            return
        if "=" in text:
            text = text.split("=", 1)[0]
        text = re.sub(r"\s*;\s*$", "", text).strip()
        if not text:
            return
        # 形如 "static UINT16 xxx;" 或 "UINT32 yyy;"
        parts = text.split()
        if len(parts) >= 2:
            name = parts[-1].strip("*&").strip()
            vtype = " ".join(parts[:-1]).strip()
            if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                g = GlobalVariable()
                g.name = name
                g.type = vtype
                result.globals.append(g)

    # ---------- 函数解析 ----------

    def parse_function(self, node):
        f = FunctionInfo()
        f.body = self._text(node).strip()

        # 提取函数前置注释块（连续的前置 comment 节点）
        f.pre_comment = self._collect_pre_comment(node)

        declarator = node.child_by_field_name("declarator")
        if declarator is not None:
            f.name = self.find_identifier(declarator)

        if not self.is_valid_name(f.name):
            f.name = ""

        # 返回类型：children[0] 通常是类型节点（primitive_type /
        # type_identifier / declaration_specifiers），需要处理 static
        # 以及返回指针的情况（declarator 为 pointer_declarator）
        for child in node.children:
            if child.type == "storage_class_specifier":
                if "static" in self._strip(child):
                    f.is_static = True
            elif child.type in (
                "primitive_type",
                "type_identifier",
                "sized_type_specifier",
            ):
                f.return_type = self._strip(child)
                break
            elif child.type == "declaration_specifiers":
                # 递归找类型
                for c in child.children:
                    if c.type in (
                        "primitive_type",
                        "type_identifier",
                        "sized_type_specifier",
                    ):
                        f.return_type = self._strip(c)
                        break

        # 返回指针类型：declarator 是 pointer_declarator 时补上 *
        if declarator is not None and declarator.type == "pointer_declarator":
            ptr_part = self._strip(declarator)
            if ptr_part and ptr_part[0] == "*":
                f.return_type = (f.return_type + " *").strip()

        # 参数列表
        pl = self.find_node(declarator, "parameter_list")
        if pl is not None:
            for child in pl.children:
                if child.type == "parameter_declaration":
                    f.parameters.append(self.parse_parameter(child))

        # 局部变量
        f.local_variables = self.parse_local_variables(node)

        # 调用关系
        f.calls = self.parse_calls(node)

        # 流程树
        body_node = node.child_by_field_name("body")
        if body_node is not None:
            f.flow = self.parse_flow_node(body_node)
            if f.flow.kind in ("block", "compound"):
                f.flow.kind = "block"

        # 函数前注释（简单启发式：正文前的连续注释行，此处略）
        return f

    def find_node(self, node, ntype):
        """在子树中查找第一个指定类型节点（先序遍历）。"""
        if node is None:
            return None
        if node.type == ntype:
            return node
        for child in node.children:
            r = self.find_node(child, ntype)
            if r is not None:
                return r
        return None

    def _collect_pre_comment(self, node):
        """收集函数定义前的连续注释块，返回拼接文本。"""
        parts = []
        cur = getattr(node, "prev_named_sibling", None)
        while cur is not None and cur.type == "comment":
            parts.append(self._strip(cur))
            cur = getattr(cur, "prev_named_sibling", None)
        parts.reverse()
        return "\n".join(parts)

    def find_identifier(self, node):
        """在子树中查找第一个 identifier/field_identifier 节点文本。"""
        if node is None:
            return ""
        if node.type in ("identifier", "field_identifier"):
            return self._strip(node)
        for child in node.children:
            name = self.find_identifier(child)
            if name:
                return name
        return ""

    def parse_parameter(self, node):
        """解析 parameter_declaration -> ParameterInfo。

        parameter_declaration 结构：
          - type 字段：primitive_type / type_identifier 等类型节点
          - declarator 字段：identifier / pointer_declarator /
            array_declarator / function_declarator

        输出：type 只含类型部分（如 "UINT8*"、"UINT8 [8]"），
              name 只含参数名（如 "sendBuf"）。
        """
        p = ParameterInfo()
        type_node = node.child_by_field_name("type")
        decl_node = node.child_by_field_name("declarator")
        base_type = self._strip(type_node) if type_node is not None else ""
        if decl_node is None:
            p.type = base_type
            p.name = ""
            return p
        p.name = self.find_identifier(decl_node)
        # 从声明符文本中剥离名字，得到 " *" / "[8]" / "" 等后缀
        suffix = self._strip(decl_node)
        if p.name:
            suffix = suffix.replace(p.name, "", 1).strip()
        # 类型规范化：数组 "buf[3]" -> 后缀 "[3]"，拼接为 "UINT8[3]"
        p.type = (base_type + " " + suffix).strip()
        p.type = p.type.replace(" [", "[").replace("  ", " ")
        return p

    # ---------- struct / enum ----------

    def parse_struct(self, node):
        s = StructInfo()
        s.raw = self._strip(node)
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            s.name = self._strip(name_node)
        else:
            # 匿名 struct：从 typedef 父节点获取类型名
            parent = node.parent
            if parent is not None and parent.type == "type_definition":
                for c in parent.children:
                    if c.type == "type_identifier":
                        s.name = self._strip(c)
                        break
            if s.name == "" or s.name == "anonymous":
                s.name = "anonymous"
        body_node = node.child_by_field_name("body")
        if body_node is None:
            # 前向声明/引用（如 struct Node* next），不是定义
            return None
        for field in body_node.children:
            if field.type == "field_declaration":
                t = field.child_by_field_name("type")
                type_txt = self._strip(t) if t is not None else ""
                # 声明符可能是 field_identifier 或 pointer_declarator/array_declarator
                d = field.child_by_field_name("declarator")
                if d is None:
                    continue
                name = self.find_identifier(d)
                if name:
                    suffix = self._strip(d).replace(name, "", 1).strip()
                    s.members.append({
                        "name": name,
                        "type": (type_txt + " " + suffix).strip()
                    })
        return s

    def parse_enum(self, node):
        e = EnumInfo()
        e.raw = self._strip(node)
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            e.name = self._strip(name_node)
        else:
            parent = node.parent
            if parent is not None and parent.type == "type_definition":
                for c in parent.children:
                    if c.type == "type_identifier":
                        e.name = self._strip(c)
                        break
            if e.name == "" or e.name == "anonymous":
                e.name = "anonymous"
        body_node = node.child_by_field_name("body")
        if body_node is None:
            return None
        last_value = -1
        for enum in body_node.children:
            if enum.type == "enumerator":
                ename = None
                evalue = ""
                for c in enum.children:
                    if c.type == "identifier":
                        ename = self._strip(c)
                    elif c.type == "number_literal":
                        evalue = self._strip(c)
                if ename:
                    if evalue:
                        try:
                            last_value = int(evalue, 0)
                        except ValueError:
                            last_value = -1
                    else:
                        # 自动递增
                        last_value += 1
                        evalue = str(last_value)
                    e.items.append({"name": ename, "value": evalue})
        return e

    # ---------- 局部变量 ----------

    def parse_local_variables(self, func_node):
        """解析函数体内的局部变量声明。"""
        variables = []
        body_node = func_node.child_by_field_name("body")
        if body_node is None:
            return variables
        for decl in body_node.children:
            if decl.type == "declaration":
                t = decl.child_by_field_name("type")
                type_txt = self._strip(t) if t is not None else ""
                for c in decl.children:
                    if c.type == "init_declarator":
                        name = self.find_identifier(c)
                        if name:
                            variables.append({"type": type_txt, "name": name})
                    elif c.type == "pointer_declarator":
                        name = self.find_identifier(c)
                        if name:
                            variables.append({"type": type_txt + "*", "name": name})
        return variables

    # ---------- 调用关系 ----------

    def parse_calls(self, func_node):
        calls = []
        stack = [func_node]
        keywords = {
            "if", "for", "while", "switch", "sizeof", "return",
            "do", "else", "case", "break", "continue", "goto",
        }
        while stack:
            n = stack.pop()
            if n.type == "call_expression":
                fn = n.child_by_field_name("function")
                if fn is not None and fn.type == "identifier":
                    name = self._strip(fn)
                    if name not in keywords and name not in calls:
                        calls.append(name)
            stack.extend(n.children)
        return calls

    # ---------- 流程树 ----------

    def _clean_comment(self, text):
        """清理注释文本：去掉 /*、*/、/**、/*-、行首星号和多余空白。"""
        if not text:
            return ""
        lines = []
        for ln in text.split("\n"):
            ln = ln.strip()
            ln = re.sub(r'^/\*[-*]*\s*', '', ln)  # 去 /* 、/** 、/*-
            ln = re.sub(r'\s*\*/\s*$', '', ln)    # 去 */
            ln = re.sub(r'^\*\s*', '', ln)        # 去行首 *
            lines.append(ln)
        # 合并为单行（去掉空行）
        joined = " ".join(l for l in lines if l)
        return re.sub(r'\s+', ' ', joined).strip()

    def _find_pre_comment(self, node):
        """取节点前最近的注释块（连续 comment 节点），清理后返回。"""
        cur = getattr(node, "prev_named_sibling", None)
        parts = []
        while cur is not None and cur.type == "comment":
            parts.append(self._strip(cur))
            cur = getattr(cur, "prev_named_sibling", None)
        if not parts:
            return ""
        parts.reverse()
        return self._clean_comment("\n".join(parts))

    def parse_flow_node(self, node):
        """把单个语句/代码块解析为流程树。"""
        ntype = node.type

        # 注释不是执行步骤，跳过
        if ntype == "comment":
            return None

        if ntype == "compound_statement":
            return self._parse_compound_block(node)

        # 其余单语句（if/while/for/switch/return/expression/declaration...）
        return self._parse_statement(node)

    def _parse_compound_block(self, node):
        """解析函数体/代码块，以注释为块边界。

        规则：
          - 遇到注释 -> 记录为当前块标签
          - 遇到普通语句（表达式/声明）：
              * 有当前块标签 -> 并入该块（作为块内容的一部分）
              * 无块标签 -> 单独成块（用代码文本）
          - 遇到分支/循环（if/while/for/switch）：
              * 该节点本身是一个独立块，用其前置注释作标签
              * 内部递归按同样规则
        """
        block = FlowNode("block")
        current_label = None
        current_items = []  # 当前标签块内收集的语句文本

        def flush():
            nonlocal current_label, current_items
            if current_label is not None:
                # 注释块：label=注释，内容可含多条语句（简化：合并成单块）
                block.add(FlowNode("sequence", current_label))
            else:
                # 无注释的语句逐个成块
                for item in current_items:
                    block.add(FlowNode("sequence", item))
            current_label = None
            current_items = []

        for child in node.children:
            ctype = child.type
            if ctype in ("{", "}"):
                continue
            if ctype == "comment":
                # 遇到注释：先 flush 上一个块，再开始新块
                flush()
                current_label = self._clean_comment(self._strip(child))
                current_items = []
                continue
            if ctype in ("if_statement", "while_statement", "for_statement",
                         "do_statement", "switch_statement",
                         "return_statement", "break_statement",
                         "continue_statement", "goto_statement",
                         "labeled_statement"):
                # 分支/循环/返回等：独立块
                # 若 pending 的注释恰是该分支自身的前置注释，则丢弃（不重复建块）
                branch_comment = self._find_pre_comment(child)
                if current_label is not None and branch_comment and \
                        current_label == branch_comment:
                    current_label = None
                    current_items = []
                flush()
                sub = self.parse_flow_node(child)
                if sub is not None:
                    block.add(sub)
                continue
            # 普通语句（表达式/声明）
            stmt_node = self.parse_flow_node(child)
            if stmt_node is not None:
                if current_label is not None:
                    # 并入当前注释块（丢弃语句文本，块已由注释命名）
                    pass
                else:
                    current_items.append(stmt_node.label)

        flush()
        return block

    def _parse_statement(self, node):
        """把单个语句解析为流程节点。"""
        ntype = node.type

        if ntype == "if_statement":
            cond_node = node.child_by_field_name("condition")
            then_node = node.child_by_field_name("consequence")
            else_node = node.child_by_field_name("alternative")
            if_node = FlowNode("if")
            # 分支标签：优先用上一行注释，无注释用条件表达式（英文）
            comment = self._find_pre_comment(node)
            if_node.condition = comment if comment else (self._strip(cond_node) if cond_node else "条件")
            if then_node is not None:
                then_flow = self.parse_flow_node(then_node)
                if then_flow is not None:
                    if_node.children.append(then_flow)
            if else_node is not None:
                else_flow = FlowNode("else")
                # else_clause 可能包含嵌套 if_statement（else if 链）
                if else_node.type == "else_clause":
                    for c in else_node.children:
                        if c.type == "else":
                            continue
                        sub = self.parse_flow_node(c)
                        if sub is not None:
                            if sub.kind == "block":
                                else_flow.children = sub.children
                            else:
                                else_flow.children.append(sub)
                else:
                    sub = self.parse_flow_node(else_node)
                    if sub is not None:
                        if sub.kind == "block":
                            else_flow.children = sub.children
                        else:
                            else_flow.children.append(sub)
                if_node.alternate = else_flow
            return if_node
        if ntype == "for_statement":
            loop = FlowNode("for")
            init = node.child_by_field_name("initializer")
            cond = node.child_by_field_name("condition")
            update = node.child_by_field_name("update")
            body = node.child_by_field_name("body")
            # 循环标签：优先用上一行注释，无注释用 init;cond;update
            comment = self._find_pre_comment(node)
            parts = []
            if init is not None:
                parts.append(self._strip(init))
            if cond is not None:
                parts.append(self._strip(cond))
            if update is not None:
                parts.append(self._strip(update))
            loop.condition = comment if comment else "; ".join(parts)
            if body is not None:
                body_flow = self.parse_flow_node(body)
                if body_flow is not None:
                    if body_flow.kind == "block":
                        loop.children = body_flow.children
                    else:
                        loop.children.append(body_flow)
            return loop

        if ntype == "while_statement":
            loop = FlowNode("while")
            cond = node.child_by_field_name("condition")
            # 循环标签：优先用上一行注释，无注释用条件表达式
            comment = self._find_pre_comment(node)
            loop.condition = comment if comment else (self._strip(cond) if cond else "")
            body = node.child_by_field_name("body")
            if body is not None:
                body_flow = self.parse_flow_node(body)
                if body_flow is not None:
                    if body_flow.kind == "block":
                        loop.children = body_flow.children
                    else:
                        loop.children.append(body_flow)
            return loop

        if ntype == "do_statement":
            loop = FlowNode("do_while")
            body = node.child_by_field_name("body")
            cond = node.child_by_field_name("condition")
            if body is not None:
                body_flow = self.parse_flow_node(body)
                if body_flow is not None:
                    if body_flow.kind == "block":
                        loop.children = body_flow.children
                    else:
                        loop.children.append(body_flow)
            loop.condition = self._strip(cond) if cond else ""
            # do-while 标签：优先用上一行注释
            comment = self._find_pre_comment(node)
            if comment:
                loop.condition = comment
            return loop

        if ntype == "switch_statement":
            sw = FlowNode("switch")
            cond = node.child_by_field_name("condition")
            # switch 标签：优先用上一行注释
            comment = self._find_pre_comment(node)
            sw.condition = comment if comment else (self._strip(cond) if cond else "")
            body = node.child_by_field_name("body")
            if body is not None:
                # body 是 compound_statement，遍历 case_statement
                for child in body.children:
                    if child.type == "case_statement":
                        case = FlowNode("case")
                        text = self._strip(child)
                        if text.startswith("default"):
                            case.kind = "default"
                            case.label = "default"
                        else:
                            val = child.child_by_field_name("value")
                            case.label = self._strip(val) if val else ""
                        # case 节点内部包含语句
                        for c in child.children:
                            if c.type in ("case", "default", ":", ";",
                                          "identifier", "expression_list"):
                                continue
                            if c.type in ("identifier",) and c == child.child_by_field_name("value"):
                                continue
                            stmt = self.parse_flow_node(c)
                            if stmt is not None:
                                case.add(stmt)
                        sw.add(case)
                    elif child.type not in ("{", "}"):
                        stmt = self.parse_flow_node(child)
                        if stmt is not None:
                            sw.add(stmt)
            return sw

        if ntype == "return_statement":
            ret = FlowNode("return")
            # return 标签：优先用上一行注释，无注释用 return 表达式（英文）
            comment = self._find_pre_comment(node)
            if comment:
                ret.label = comment
            else:
                # return 后跟表达式：children 通常为 [return, 表达式, ;]
                for ch in node.children:
                    if ch.type == "return":
                        continue
                    if ch.type == ";":
                        continue
                    ret.label = self._strip(ch)
                    break
            return ret

        if ntype == "break_statement":
            return FlowNode("break")
        if ntype == "continue_statement":
            return FlowNode("continue")
        if ntype == "goto_statement":
            label = node.child_by_field_name("label")
            return FlowNode("sequence", "goto " + (self._strip(label) if label else ""))
        if ntype == "labeled_statement":
            label = node.child_by_field_name("label")
            sub = None
            for c in node.children:
                if c.type not in ("label", ":"):
                    sub = c
                    break
            lab = FlowNode("sequence", "label: " + (self._strip(label) if label else ""))
            if sub is not None:
                sub_node = self.parse_flow_node(sub)
                if sub_node is not None:
                    lab.add(sub_node)
            return lab

        if ntype == "expression_statement":
            # 步骤标签：优先用上一行注释，无注释用表达式（英文）
            comment = self._find_pre_comment(node)
            if comment:
                return FlowNode("sequence", comment)
            # expression_statement 无 expression 字段名，直接取第一个非分号子节点
            label = ""
            for ch in node.children:
                if ch.type == ";":
                    continue
                label = self._strip(ch)
                break
            label = label.rstrip(";")
            if label:
                return FlowNode("sequence", label)
            return None

        if ntype == "declaration":
            # 变量声明步骤：优先用上一行注释，无注释用声明原文
            comment = self._find_pre_comment(node)
            if comment:
                return FlowNode("sequence", comment)
            label = self._strip(node).rstrip(";").strip()
            if label:
                return FlowNode("sequence", label)
            return None

        # 其他未知语句类型：作为顺序步骤（取文本首行）
        text = self._strip(node)
        if text:
            first = text.splitlines()[0].strip()[:60]
            if first:
                return FlowNode("sequence", first)
        return None

    # ---------- 工具 ----------

    def is_valid_name(self, name):
        return re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name) is not None
