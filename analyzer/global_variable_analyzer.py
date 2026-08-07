# -*- coding: utf-8 -*-
"""全局变量引用/修改分析器。

对每个函数，判断它引用了哪些全局变量、修改了哪些全局变量。

规则：
- 引用(global_refs)：函数体内出现全局变量名（作为右值/读操作）。
- 修改(global_mods)：函数体内出现全局变量名且伴随赋值（= 或
  自增/自减 ++ --，或作为 & 取址后传入）。
- 同名局部变量/参数优先：若函数内声明了同名局部变量或参数，
  则该名字视为局部，不计入全局。

为了让分析器独立、可测试，分析时需要传入全局变量名字典
{名字: 类型}。若未传入，则仅基于函数体内出现的标识符（无法
区分同名局部）做保守处理。
"""

import re


class GlobalVariableAnalyzer:
    def __init__(self, globals_list=None):
        """globals_list: [GlobalVariable] 或 [{"name":..., "type":...}]"""
        self.globals = {}
        if globals_list:
            for g in globals_list:
                name = g.get("name") if isinstance(g, dict) else g.name
                if name:
                    self.globals[name] = (
                        g.get("type") if isinstance(g, dict) else g.type
                    )

    def analyze(self, function):
        body = function.body
        # 函数内的局部名字（参数 + 局部变量声明）优先
        local_names = set()
        for p in function.parameters:
            if p.name:
                local_names.add(p.name)
        for v in function.local_variables:
            if isinstance(v, dict):
                local_names.add(v.get("name", ""))
            else:
                local_names.add(v.name)

        refs = []
        mods = []

        for gname in self.globals:
            if gname in local_names:
                continue
            if not re.search(r'\b' + re.escape(gname) + r'\b', body):
                continue

            # 修改检测：gname 出现在赋值/自增/自减/取址 的场景
            is_modified = False
            # = gname / gname = / gname++ / gname-- / &gname / gname += 等
            if re.search(r'\b' + re.escape(gname) + r'\b\s*(\+\+|--|[\+\-\*/%&|^]?=)', body):
                is_modified = True
            if re.search(r'&\s*\b' + re.escape(gname) + r'\b', body):
                is_modified = True
            # 数组/结构体成员整体视为引用，不做修改判断的精细拆分

            refs.append(gname)
            if is_modified:
                mods.append(gname)

        function.global_refs = refs
        function.global_mods = mods
        return function
