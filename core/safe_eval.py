
import ast, math
_ALLOWED = {k: getattr(math, k) for k in ["pi","e","tau","sqrt","sin","cos","tan","log","log10","exp","fabs","floor","ceil","pow"]}
_ALLOWED.update({"true": True, "false": False})
class SafeEval(ast.NodeVisitor):
    def __init__(self, variables=None): self.vars = dict(variables or {})
    def eval(self, expr: str):
        tree = ast.parse(expr, mode="eval"); return self.visit(tree.body)
    def visit_Constant(self, n): return n.value
    def visit_Name(self, n):
        if n.id in self.vars: return self.vars[n.id]
        if n.id in _ALLOWED: return _ALLOWED[n.id]
        raise ValueError(f"Name '{n.id}' not allowed")
    def visit_BinOp(self,n):
        l,r=self.visit(n.left),self.visit(n.right)
        import ast as A
        return {A.Add:l+r, A.Sub:l-r, A.Mult:l*r, A.Div:l/r, A.FloorDiv:l//r, A.Mod:l%r, A.Pow:l**r}[type(n.op)]
    def visit_UnaryOp(self,n):
        import ast as A
        o=self.visit(n.operand); return {A.UAdd:+o, A.USub:-o, A.Not:(not o)}[type(n.op)]
    def visit_Compare(self,n):
        l=self.visit(n.left)
        import ast as A
        for op,c in zip(n.ops,n.comparators):
            r=self.visit(c)
            ok={A.Eq:l==r,A.NotEq:l!=r,A.Gt:l>r,A.GtE:l>=r,A.Lt:l<r,A.LtE:l<=r}[type(op)]
            if not ok: return False
            l=r
        return True
    def visit_Call(self,n):
        if isinstance(n.func, ast.Name) and n.func.id in _ALLOWED:
            f=_ALLOWED[n.func.id]; args=[self.visit(a) for a in n.args]; return f(*args)
        raise ValueError("Function calls are restricted")
    def generic_visit(self, node): raise ValueError(f"Unsupported: {type(node).__name__}")
