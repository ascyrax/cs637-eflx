"""Fast version of model.Plan: same equations, built as one sparse matrix for HiGHS.

model.Plan (cvxpy) is the readable spec; this file is what we run at Manhattan
scale. tests/test_fastplan.py checks both give identical optimal values.

A linear expression is a 1 x N scipy sparse row; constraints are lo <= expr <= hi.
"""
import highspy
import numpy as np
import scipy.sparse as sp

INF = highspy.kHighsInf


class FastPlan:
    def __init__(self, city, state, t0, H):
        c = self.city = city
        self.t0, self.H = t0, H
        L, n, m = c.L, c.n, c.m
        self.N = 0
        self.lb, self.ub = [], []
        self._r, self._c, self._v, self.lo, self.hi = [], [], [], [], []
        self.R = 0

        X = self.X = self._var((H, L, n, m))
        Y = self.Y = self._var((H, L, n, n))
        XD = self.XD = self._var((H, L, m, m))
        YD = self.YD = self._var((H, L, m, n))
        U = self.U = self._var((H, L, m))
        S = self._var((H, L, n))
        V = self.Vv = self._var((H + 1, L, n))
        O = self.Ov = self._var((H + 1, L, n))
        D = self.Dv = self._var((H + 1, L, m))
        J = self._var((H, n))
        lb, ub = self.lb, self.ub

        # measured state at slot 0 (fixed through bounds)
        for var, val in ((V[0], state.V), (O[0], state.O), (D[0], state.D)):
            lb[var] = ub[var] = val
        # Eq. (5e)/(5f): unreachable destinations
        ub[X[:, :, ~c.reach_rs]] = 0
        ub[Y[:, :, ~c.reach_rr]] = 0
        ub[XD[:, :, ~c.reach_ss]] = 0
        ub[YD[:, :, ~c.reach_rs.T]] = 0
        # Eq. (5g): low-battery taxis do not serve (S is a sum of y, yd >= 0)
        ub[Y[:, :c.L1 + 1]] = 0
        ub[YD[:, :c.L1 + 1]] = 0
        ub[S[:, :c.L1 + 1]] = 0
        # charge only if a full slot fits
        ub[U[:, c.max_charge_level + 1:]] = 0
        # J <= r (J_trans = sum min(r, S))
        ub[J] = c.demand[t0:t0 + H]

        # Eq. (1)
        self._eq([(X, 1), (Y, 1), (V[:H], -1)], (H, L, n))
        self._eq([(XD, 1), (YD, 1), (D[:H], -1)], (H, L, m))
        # Eq. (2a): S = incoming y + incoming yd
        self._eq([(S, -1), (Y.transpose(0, 1, 3, 2), 1), (YD.transpose(0, 1, 3, 2), 1)], (H, L, n))
        # Eq. (3): u <= arrivals,  sum_l u <= ports
        A = [(X.transpose(0, 1, 3, 2), 1), (XD.transpose(0, 1, 3, 2), 1)]
        self._rows([(U, 1)] + [(a, -1) for a, _ in A], (H, L, m), -INF, 0)
        self._rows([(U.transpose(0, 2, 1), 1)], (H, m), -INF, np.broadcast_to(c.ports, (H, m)))
        # J <= sum_l S
        self._rows([(J, 1), (S.transpose(0, 2, 1), -1)], (H, n), -INF, 0)

        # Eq. (2b), (2c): mobility, one block per source level l (target level drop(l))
        tt = np.arange(t0, t0 + H)
        for nxt, Pm, Qm in ((V, c.Pv, c.Qv), (O, c.Po, c.Qo)):
            rows = self._new_rows((H, L, n), 0, 0)
            self._add(rows, nxt[1:], 1)
            for l in range(L):
                d = max(l - c.L1, 0)
                # row (k, d, i) gets -sum_i' P[t][i', i] * S[k, l, i']
                self._add(rows[:, d, :, None], S[:, l, None, :], -Pm[tt].transpose(0, 2, 1))
                self._add(rows[:, d, :, None], O[:H, l, None, :], -Qm[tt].transpose(0, 2, 1))
        # Eq. (4): D' = u[l-L2] + arrivals - u
        rows = self._new_rows((H, L, m), 0, 0)
        self._add(rows, D[1:], 1)
        self._add(rows, U, 1)
        self._add(rows[:, :, :, None], X.transpose(0, 1, 3, 2), -1)
        self._add(rows[:, :, :, None], XD.transpose(0, 1, 3, 2), -1)
        self._add(rows[:, c.L2:], U[:, :L - c.L2], -1)

        # expressions used by the policies
        lv = np.arange(L, dtype=float)
        self.served = [self.expr(J[k], 1) for k in range(H)]
        self.charge = [self.expr(U[k], 1) for k in range(H)]
        self.at_station = [self.expr(np.concatenate([X[k].ravel(), XD[k].ravel()]), 1) for k in range(H)]
        self.idle = [self.expr(np.concatenate([X[k].ravel(), YD[k].ravel(), Y[k].ravel(), XD[k].ravel()]),
                               np.concatenate([np.broadcast_to(c.phi, X[k].shape).ravel(),
                                               np.broadcast_to(c.phi.T, YD[k].shape).ravel(),
                                               np.broadcast_to(c.mu, Y[k].shape).ravel(),
                                               np.broadcast_to(c.vss, XD[k].shape).ravel()]))
                     for k in range(H)]
        self.energy = [self.expr(np.concatenate([V[k + 1].ravel(), O[k + 1].ravel(), D[k + 1].ravel()]),
                                 np.concatenate([np.repeat(lv, n), np.repeat(lv, n), np.repeat(lv, m)]))
                       for k in range(H)]

    # ---------- building blocks ----------
    def _var(self, shape):
        size = int(np.prod(shape))
        idx = np.arange(self.N, self.N + size).reshape(shape)
        self.N += size
        self.lb = np.concatenate([self.lb, np.zeros(size)]) if len(self.lb) else np.zeros(size)
        self.ub = np.concatenate([self.ub, np.full(size, INF)]) if len(self.ub) else np.full(size, INF)
        return idx

    def _new_rows(self, shape, lo, hi):
        size = int(np.prod(shape))
        rows = np.arange(self.R, self.R + size).reshape(shape)
        self.R += size
        self.lo.append(np.broadcast_to(lo, shape).ravel().astype(float))
        self.hi.append(np.broadcast_to(hi, shape).ravel().astype(float))
        return rows

    def _add(self, rows, cols, coef):
        rows, cols = np.broadcast_arrays(rows[(...,) + (None,) * (cols.ndim - rows.ndim)], cols)
        coef = np.broadcast_to(coef, cols.shape)
        self._r.append(rows.ravel()); self._c.append(cols.ravel()); self._v.append(coef.ravel().astype(float))

    def _rows(self, terms, shape, lo, hi):
        rows = self._new_rows(shape, lo, hi)
        for cols, coef in terms:
            self._add(rows, cols, coef)

    def _eq(self, terms, shape):
        self._rows(terms, shape, 0, 0)

    # ---------- public API (mirrors model.Plan) ----------
    def expr(self, cols, coef):
        cols = np.asarray(cols).ravel()
        coef = np.broadcast_to(coef, cols.shape)
        return sp.csr_matrix((coef.astype(float), (np.zeros(len(cols), int), cols)), shape=(1, self.N))

    def add(self, e, lo=-INF, hi=INF):
        e = e.tocoo()
        r = self._new_rows((1,), lo, hi)[0]
        self._r.append(np.full(e.nnz, r)); self._c.append(e.col); self._v.append(e.data)

    def fix_first_slots(self, decisions_list):
        for k, dec in enumerate(decisions_list):
            for var, key in ((self.X, "x"), (self.Y, "y"), (self.XD, "xd"), (self.YD, "yd"), (self.U, "u")):
                self.lb[var[k]] = self.ub[var[k]] = np.asarray(dec[key])

    def solve(self, objective, maximize=False):
        A = sp.csc_matrix((np.concatenate(self._v), (np.concatenate(self._r), np.concatenate(self._c))),
                          shape=(self.R, self.N))
        cost = objective.toarray().ravel() * (-1 if maximize else 1)
        h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        h.setOptionValue("threads", 1)   # we parallelise across experiments instead
        lp = highspy.HighsLp()
        lp.num_col_, lp.num_row_ = self.N, self.R
        lp.col_cost_, lp.col_lower_, lp.col_upper_ = cost, self.lb, self.ub
        lp.row_lower_, lp.row_upper_ = np.concatenate(self.lo), np.concatenate(self.hi)
        lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = A.indptr, A.indices, A.data
        h.passModel(lp)
        h.run()
        status = h.modelStatusToString(h.getModelStatus())
        if status != "Optimal":
            raise RuntimeError(f"LP status {status} at t0={self.t0}")
        self.sol = np.array(h.getSolution().col_value)
        return float(cost @ self.sol) * (-1 if maximize else 1)

    def value(self, e):
        return float((e @ self.sol)[0])

    def values(self, exprs):
        return np.array([self.value(e) for e in exprs])

    def decisions(self, k=0):
        g = lambda var: np.clip(self.sol[var[k]], 0, None)
        return dict(x=g(self.X), y=g(self.Y), xd=g(self.XD), yd=g(self.YD), u=g(self.U))
