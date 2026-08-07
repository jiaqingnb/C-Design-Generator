class DescriptionAnalyzer:


    def analyze(self,function):


        name=function.name


        function.description=(

            "该函数用于执行 "

            +

            name

            +

            " 相关处理流程。"

        )


        return function