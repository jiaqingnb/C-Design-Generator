class FileLoader:
    """读取源文件。

    注意：必须保留原始字节，因为 tree-sitter 的 start_byte/end_byte
    是字节偏移，而 Python 字符串索引是字符偏移。中文字符在 UTF-8 下
    每字 3 字节，若先用文本模式读取（还会做 CRLF→LF 转换），
    会导致字节偏移与字符索引错位，切片全部取错。

    编码处理：C 源文件可能是 UTF-8 或 GBK/GB2312。load() 读入原始字节后
    做编码归一化——检测并统一转成 UTF-8 字节返回。这样 tree-sitter 解析
    和 ast_parser 的 utf-8 解码全链路一致，GBK 中文不会变成乱码。
    """

    def load(self, filename):
        try:
            with open(filename, "rb") as f:
                raw = f.read()
            return self._normalize_encoding(raw)
        except Exception as e:
            print("读取文件失败:", e)
            return None

    @staticmethod
    def _normalize_encoding(data):
        """把源文件字节统一转成 UTF-8 编码。

        策略：先尝试 UTF-8 严格解码；失败则视为 GBK（兼容 GB2312），
        用 GBK 解码后重新编码为 UTF-8。
        """
        if not data:
            return data
        # 尝试 UTF-8 严格解码（BOM 也处理）
        try:
            if data.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
                return data[3:]
            data.decode("utf-8")
            return data  # 本身就是合法 UTF-8，原样返回
        except UnicodeDecodeError:
            pass
        # UTF-8 失败 -> 按 GBK/GB2312 解码（GBK 是 GB2312 超集），再转回 UTF-8
        try:
            return data.decode("gbk").encode("utf-8")
        except UnicodeDecodeError:
            # GBK 也失败：退回最宽容的方式，用 UTF-8 + replace 兜底
            return data.decode("utf-8", errors="replace").encode("utf-8")

    @staticmethod
    def decode(data):
        if data is None:
            return ""
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return data
