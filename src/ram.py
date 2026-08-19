"""
2D ramanalys med direkta styvhetsmetoden.

Stodjer:
  - normalkraft + boj (3 frihetsgrader per nod: ux, uy, rz)
  - ledslapp i elementanda (statisk kondensering) -> tre- eller tvaledsram
  - ROTATIONSFJADER i elementanda (samma kondensering med fjaderstyvhet;
    S = 0 ger led, S -> oandligt ger styv anslutning)
  - SKJUVDEFORMATION (Timoshenko) nar GA anges pa elementet. Utan GA ar
    elementet Euler-Bernoulli, precis som fore. Alla slutna losningar i
    tests/test_ram.py galler ofortsatt for GA = None.
  - jamnt utbredd last i global y-riktning per meter ELEMENTLANGD, och
    last vinkelratt elementet (lokal y) for t.ex. vindtryck mot takytan
  - snittkrafter langs elementet

Teckenkonvention
  Global: x at hoger, y uppat, rotation moturs positiv.
  Element: S = k*d + S0 = krafter som noderna anbringar PA elementet.
  Lokal y pekar at vanster om lokala x-riktningen, dvs for en sparre som
  gar uppat ar lokal y utatriktad normal till takytan.
  Snittmoment M(x) redovisas positivt vid dragning i underkant (sag).

Timoshenko: styvhetsmatrisen modifieras med phi = 12EI/(GA*L^2) enligt
standardformuleringen. Fastinspanningskrafterna for jamn last ar oforandrade
(wL/2, wL^2/12) -- de ar exakta aven for Timoshenkobalken av symmetriskal.
Nodforskjutningarna ar darmed nodexakta aven med skjuvdeformation.
"""

import numpy as np


class Frame:
    def __init__(self):
        self.nodes = []        # [(x, y)]
        self.elements = []     # dict
        self.supports = {}     # node -> (fix_ux, fix_uy, fix_rz)
        self.nodal_loads = {}  # node -> (Fx, Fy, M)

    # -- uppbyggnad ---------------------------------------------------------

    def add_node(self, x, y):
        self.nodes.append((float(x), float(y)))
        return len(self.nodes) - 1

    def add_element(self, i, j, EA, EI, release_i=False, release_j=False,
                    GA=None, spring_i=None, spring_j=None):
        """
        GA        skjuvstyvhet [kN]. None = Euler-Bernoulli (ingen
                  skjuvdeformation). ETA 12/0018 tab. 11/12 deklarerar GA.
        spring_i  rotationsfjader [kNm/rad] mellan elementanden och noden.
                  None = styv koppling. 0.0 = led (samma som release).
                  release_i/j ar kvar som bekvamlighet och betyder fjader 0.
        """
        self.elements.append(dict(i=i, j=j, EA=float(EA), EI=float(EI),
                                  ri=bool(release_i), rj=bool(release_j),
                                  si=spring_i, sj=spring_j,
                                  GA=GA, w=0.0, wp=0.0))
        return len(self.elements) - 1

    def add_support(self, node, ux=False, uy=False, rz=False):
        self.supports[node] = (ux, uy, rz)

    def add_nodal_load(self, node, Fx=0.0, Fy=0.0, M=0.0):
        fx, fy, m = self.nodal_loads.get(node, (0.0, 0.0, 0.0))
        self.nodal_loads[node] = (fx + Fx, fy + Fy, m + M)

    def set_udl(self, elem, w_global_y):
        """w [kN/m elementlangd], positiv uppat. Nedatlast anges negativ."""
        self.elements[elem]["w"] = float(w_global_y)

    def set_udl_projected(self, elem, w_per_horizontal):
        """
        Last angiven per meter HORISONTALPROJEKTION (sa anges snolast).
        Rakans om till last per meter elementlangd.
        """
        L, c, s = self._geom(elem)
        self.elements[elem]["w"] = float(w_per_horizontal) * abs(c)

    def set_udl_local(self, elem, q_perp):
        """
        Jamn last VINKELRATT elementet [kN/m elementlangd], positiv i lokal
        y-riktning (utat fran takytan for en sparre). Vindtryck MOT ytan ar
        alltsa negativt har. Adderas till eventuell global last.
        """
        self.elements[elem]["wp"] = float(q_perp)

    # -- geometri -----------------------------------------------------------

    def _geom(self, e):
        n = self.elements[e]
        xi, yi = self.nodes[n["i"]]
        xj, yj = self.nodes[n["j"]]
        dx, dy = xj - xi, yj - yi
        L = np.hypot(dx, dy)
        return L, dx / L, dy / L

    def _T(self, e):
        L, c, s = self._geom(e)
        t = np.zeros((6, 6))
        R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
        t[:3, :3] = R
        t[3:, 3:] = R
        return t

    def _k_local(self, e):
        n = self.elements[e]
        L, _, _ = self._geom(e)
        EA, EI = n["EA"], n["EI"]
        # Timoshenko: phi = 12EI/(GA*L^2). GA = None -> phi = 0 -> Euler.
        phi = 0.0 if n["GA"] is None else 12.0 * EI / (n["GA"] * L**2)
        k = np.zeros((6, 6))
        k[0, 0] = k[3, 3] = EA / L
        k[0, 3] = k[3, 0] = -EA / L
        f = 1.0 + phi
        a = 12*EI/(L**3 * f)
        b = 6*EI/(L**2 * f)
        c_ = (4 + phi)*EI/(L * f)
        d = (2 - phi)*EI/(L * f)
        k[1, 1] = k[4, 4] = a
        k[1, 4] = k[4, 1] = -a
        k[1, 2] = k[2, 1] = b
        k[1, 5] = k[5, 1] = b
        k[2, 4] = k[4, 2] = -b
        k[4, 5] = k[5, 4] = -b
        k[2, 2] = k[5, 5] = c_
        k[2, 5] = k[5, 2] = d
        return k

    def _s0_local(self, e):
        """Fastinspanningskrafter for jamn last, uttryckt lokalt."""
        n = self.elements[e]
        L, c, s = self._geom(e)
        w = n["w"]                       # global y, per m elementlangd
        q_perp = w * c + n["wp"]         # lokal y: global + direkt lokal
        q_ax = w * s                     # komponent langs elementet
        return np.array([
            -q_ax * L / 2, -q_perp * L / 2, -q_perp * L**2 / 12,
            -q_ax * L / 2, -q_perp * L / 2,  q_perp * L**2 / 12,
        ]), q_perp, q_ax

    @staticmethod
    def _fjader_kondensering(k, s0, c, S):
        """
        Kondenserar bort elementets EGEN androtation vid index c och
        ersatter den med en rotationsfjader S [kNm/rad] mot noden.

        Harledning: lat theta_e vara elementets androtation och theta_n
        nodens. Fjaderenergin ar S/2*(theta_n - theta_e)^2. Eliminering av
        theta_e ur jamvikten ger, med kcc = k[c,c]:

            K_ny = K - k_c k_c^T / (kcc + S)        (ovriga frihetsgrader)
            K_ny[i,c] = k_c[i] * S/(kcc + S)
            K_ny[c,c] = S*kcc/(kcc + S)
            s0_ny = s0 - k_c s0[c]/(kcc + S),  s0_ny[c] = S*s0[c]/(kcc + S)

        S = 0 ger exakt den gamla ledkondenseringen (raden/kolonnen
        nollstalls). S -> oandligt ger tillbaka k oforandrad. Tva fjadrar
        pa samma element hanteras genom att kora funktionen tva ganger --
        de ar oberoende inre frihetsgrader, sa ordningen spelar ingen roll.
        """
        kcc = k[c, c]
        kc = k[:, c].copy()
        denom = kcc + S
        k_ny = k - np.outer(kc, kc) / denom
        skal = S / denom
        k_ny[:, c] = kc * skal
        k_ny[c, :] = kc * skal
        k_ny[c, c] = S * kcc / denom
        s0_ny = s0 - kc * (s0[c] / denom)
        s0_ny[c] = S * s0[c] / denom
        return k_ny, s0_ny

    def _condense(self, k, s0, n):
        """
        Ledslapp och rotationsfjadrar i elementandarna. En release ar en
        fjader med styvheten 0.
        """
        for idx, rel, spr in ((2, n["ri"], n["si"]), (5, n["rj"], n["sj"])):
            S = 0.0 if rel else spr
            if S is not None:
                k, s0 = self._fjader_kondensering(k, s0, idx, float(S))
        return k, s0

    # -- losning ------------------------------------------------------------

    def solve(self):
        nd = len(self.nodes) * 3
        K = np.zeros((nd, nd))
        F = np.zeros(nd)

        self._cache = []
        for e, n in enumerate(self.elements):
            T = self._T(e)
            kl = self._k_local(e)
            s0l, q_perp, q_ax = self._s0_local(e)
            klc, s0c = self._condense(kl, s0l, n)
            kg = T.T @ klc @ T
            s0g = T.T @ s0c
            dofs = self._dofs(e)
            K[np.ix_(dofs, dofs)] += kg
            F[dofs] -= s0g
            self._cache.append((T, klc, s0c, q_perp, q_ax))

        for nd_i, (fx, fy, m) in self.nodal_loads.items():
            F[3*nd_i:3*nd_i+3] += [fx, fy, m]

        fixed = []
        for nd_i, (ux, uy, rz) in self.supports.items():
            for k_, flag in enumerate((ux, uy, rz)):
                if flag:
                    fixed.append(3*nd_i + k_)
        free = [i for i in range(nd) if i not in fixed]

        d = np.zeros(nd)
        d[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
        self.d = d
        self.reactions = K @ d - F
        return d

    def _dofs(self, e):
        n = self.elements[e]
        return [3*n["i"], 3*n["i"]+1, 3*n["i"]+2,
                3*n["j"], 3*n["j"]+1, 3*n["j"]+2]

    def node_disp(self, node):
        """(ux, uy, rz) for en nod efter solve()."""
        return tuple(self.d[3*node:3*node+3])

    # -- snittkrafter -------------------------------------------------------

    def end_forces(self, e):
        """Lokala andkrafter S = k*d + S0."""
        T, klc, s0c, _, _ = self._cache[e]
        dg = self.d[self._dofs(e)]
        return klc @ (T @ dg) + s0c

    def internal(self, e, npts=41):
        """
        Returnerar (x, N, V, M) langs elementet.
        N positiv = drag. M positiv = drag i underkant (lokalt).
        """
        L, _, _ = self._geom(e)
        S = self.end_forces(e)
        _, _, _, q_perp, q_ax = self._cache[e]
        x = np.linspace(0, L, npts)
        N = -S[0] + q_ax * x             # drag positiv
        V = S[1] + q_perp * x
        M = -S[2] + S[1] * x + q_perp * x**2 / 2
        return x, N, V, M

    def summary(self):
        out = []
        for e in range(len(self.elements)):
            x, N, V, M = self.internal(e)
            k = int(np.argmax(np.abs(M)))
            out.append(dict(element=e, N_max=N[np.argmax(np.abs(N))],
                            V_max=V[int(np.argmax(np.abs(V)))],
                            M_max=M[k], x_Mmax=x[k],
                            N_i=N[0], V_i=V[0], M_i=M[0],
                            N_j=N[-1], V_j=V[-1], M_j=M[-1]))
        return out


# ---------------------------------------------------------------------------
# Fardig sadeltaksmodell
# ---------------------------------------------------------------------------

def sadeltak(L, alpha_deg, EA, EI, nock_styv=True, dragband=False,
             EA_dragband=None, upplag="ledat", n_elem=8, GA=None, K_r=None):
        """
        Bygger halva/hela sadeltaket som ram.

        L            total spannvidd [m]
        alpha_deg    taklutning [grader]
        nock_styv    True  -> momentstyv nock (tvaledsram)
                     False -> ledad nock (treledsram)
        dragband     True  -> dragband i takfotsniva, tar horisontalkraften
        upplag       'ledat' | 'fast'  (fast = inspant i vagg)
        GA           skjuvstyvhet [kN] ur ETA tab. 11/12. None = ingen
                     skjuvdeformation (Euler-Bernoulli).
        K_r          nockforbandets rotationsstyvhet [kNm/rad]. Nar den
                     anges modelleras nocken som en fjader i stallet for
                     helt styv eller helt ledad -- K_r har da foretrade
                     over nock_styv. K_r = K_ser * sum(r_i^2) enligt
                     EN 1995-1-1 7.1, se forbindare_ec5.K_ser.

        Returnerar (Frame, index-dict) dar index-dictens 'vanster'/'hoger'
        ar elementkedjor och 'vanster_noder'/'hoger_noder' nodkedjorna
        (takfot forst), for t.ex. nedbojningsberakning.
        """
        import numpy as _np
        f = _np.tan(_np.radians(alpha_deg))
        rise = L / 2 * f

        fr = Frame()
        left = fr.add_node(0.0, 0.0)
        right = fr.add_node(L, 0.0)
        apex = fr.add_node(L / 2, rise)

        # sparrar som kedjor av element for att fa snittkrafter langs balken
        def chain(a, b, release_end=False, spring_end=None):
            xa, ya = fr.nodes[a]
            xb, yb = fr.nodes[b]
            prev = a
            ids, noder = [], [a]
            for k in range(1, n_elem + 1):
                t = k / n_elem
                nb = b if k == n_elem else fr.add_node(xa + (xb-xa)*t,
                                                       ya + (yb-ya)*t)
                sista = (k == n_elem)
                ids.append(fr.add_element(
                    prev, nb, EA, EI, GA=GA,
                    release_j=(release_end and sista),
                    spring_j=(spring_end if sista else None)))
                prev = nb
                noder.append(nb)
            return ids, noder

        # Ett ledat upplag ges av upplagsvillkoret (rz fri) - INTE av ett
        # ledslapp i elementet. Bada samtidigt ger singular styvhetsmatris.
        # Nockens frihet laggs pa VANSTER kedjas sista element: antingen
        # fullt slapp (ledad), fjader (K_r) eller ingenting (styv). Hoger
        # kedja ansluter alltid styvt till apexnoden -- fjadern beskriver
        # da hela forbandets eftergivlighet mellan de tva sparrarna.
        if K_r is not None:
            vanster, vn = chain(left, apex, spring_end=float(K_r))
        else:
            vanster, vn = chain(left, apex, release_end=not nock_styv)
        hoger, hn = chain(apex, right)

        fr.add_support(left, ux=True, uy=True, rz=(upplag == "fast"))
        fr.add_support(right, ux=not dragband, uy=True,
                       rz=(upplag == "fast"))

        if dragband:
            EAd = EA_dragband if EA_dragband else EA
            fr.add_element(left, right, EAd, 1e-6,
                           release_i=True, release_j=True)

        return fr, dict(left=left, right=right, apex=apex,
                        vanster=vanster, hoger=hoger,
                        vanster_noder=vn, hoger_noder=list(reversed(hn)))


# ---------------------------------------------------------------------------
# Ramverkstakstol typ b1 (handboken s. 283, knutpunkter 5.3.5-5.3.7)
# ---------------------------------------------------------------------------

def takstol_b1(L, alpha_deg, h_stod, EA, EI, GA=None, h_hanbjalke=None,
               delar=None, nock_styv=False, n_elem=8, K_r=None,
               upplag="ledat"):
    """
    Ramverkstakstol typ b1: underram mellan tva upplag, VERTIKALA
    STODBEN vid takfot rakt over upplagen, overramar fran stodbenens
    topp till nocken, LEDAD nock och en HANBJALKE som ansluter ledat
    till bada overramarna.

    Modellval ur handboken:
      - Stodbenen ansluts MOMENTSTYVT mot bade over- och underram: sa
        raknar 5.3.5 (kontrollen dar innehaller ett knutmoment M).
      - Hanbjalken ar LEDAD i bada andar: 5.3.6:s forband overfor N och
        V; momenten i spikgrupperna ar overforingsexcentriciteter
        (M = V*e), inte ett inspanningsmoment.
      - Nocken ar LEDAD enligt 5.3.7 (galler a1, b1, c1). nock_styv och
        K_r finns for jamforelser; K_r har foretrade.
      - Horisontalkraften vid takfot gar genom stodbenet ner till
        underramen, som sjalv ar dragband mellan upplagen. Hoger upplag
        ar darfor rullagrat.

    L            spannvidd mellan upplagens centrum [m]
    h_stod       stodbenets hojd = takfotens niva over underramen [m]
    h_hanbjalke  hanbjalkens hojd OVER takfotsnivan [m]. None = ingen.
    delar        styvhetsoverstyrning per del:
                 {"underram"|"stodben"|"hanbjalke": {"EA":..,"EI":..,"GA":..}}
                 -- utelamnat far overramens EA/EI/GA.
    n_elem       elementantal per overram (och underram)

    Returnerar (Frame, ix). ix har elementkedjorna vanster/hoger (takfot
    -> nock resp. nock -> takfot), underram, stodben_v/h, hanbjalke samt
    nodkedjorna vanster_noder/hoger_noder (takfot forst),
    underram_noder (vanster forst) och hanbjalke_noder.
    """
    import numpy as _np
    if h_stod <= 0:
        raise ValueError("h_stod maste vara > 0 (stodbenets hojd)")
    f = _np.tan(_np.radians(alpha_deg))
    rise = L / 2 * f

    def styvhet(namn):
        v = (delar or {}).get(namn, {})
        return v.get("EA", EA), v.get("EI", EI), v.get("GA", GA)

    fr = Frame()
    A = fr.add_node(0.0, 0.0)                    # vanster upplag
    B = fr.add_node(L, 0.0)                      # hoger upplag
    C = fr.add_node(0.0, h_stod)                 # takfot vanster
    D = fr.add_node(L, h_stod)                   # takfot hoger
    E = fr.add_node(L / 2, h_stod + rise)        # nock

    def chain(a, b, EAx, EIx, GAx, n, release_start=False,
              release_end=False, spring_end=None):
        xa, ya = fr.nodes[a]
        xb, yb = fr.nodes[b]
        prev = a
        ids, noder = [], [a]
        for k in range(1, n + 1):
            t = k / n
            nb = b if k == n else fr.add_node(xa + (xb - xa) * t,
                                              ya + (yb - ya) * t)
            ids.append(fr.add_element(
                prev, nb, EAx, EIx, GA=GAx,
                release_i=(release_start and k == 1),
                release_j=(release_end and k == n),
                spring_j=(spring_end if k == n else None)))
            prev = nb
            noder.append(nb)
        return ids, noder

    # Hanbjalkens anslutningspunkter pa overramarna
    if h_hanbjalke is not None:
        x_hb = h_hanbjalke / f
        if not 0.05 * L / 2 < x_hb < 0.95 * L / 2:
            raise ValueError(
                f"hanbjalken hamnar pa x = {x_hb:.2f} m fran takfot "
                f"(h_hanbjalke/tan alpha); den maste ligga mellan "
                f"takfot och nock")
        H1 = fr.add_node(x_hb, h_stod + h_hanbjalke)
        H2 = fr.add_node(L - x_hb, h_stod + h_hanbjalke)
        n1 = max(2, int(round(n_elem * x_hb / (L / 2))))
        n2 = max(2, n_elem - n1)
    else:
        x_hb = H1 = H2 = None

    # Overramar. Nockens frihet laggs pa vanster kedjas sista element,
    # precis som i sadeltak(): fjader K_r, annars led om inte nock_styv.
    slapp = (K_r is None) and (not nock_styv)
    fj = float(K_r) if K_r is not None else None
    if H1 is not None:
        v1, vn1 = chain(C, H1, EA, EI, GA, n1)
        v2, vn2 = chain(H1, E, EA, EI, GA, n2,
                        release_end=slapp, spring_end=fj)
        vanster, vn = v1 + v2, vn1 + vn2[1:]
        h1, hn1 = chain(E, H2, EA, EI, GA, n2)
        h2, hn2 = chain(H2, D, EA, EI, GA, n1)
        hoger, hn = h1 + h2, hn1 + hn2[1:]
    else:
        vanster, vn = chain(C, E, EA, EI, GA, n_elem,
                            release_end=slapp, spring_end=fj)
        hoger, hn = chain(E, D, EA, EI, GA, n_elem)

    # Underram (dragband + vindsgolv), stodben, hanbjalke
    EAu, EIu, GAu = styvhet("underram")
    underram, un = chain(A, B, EAu, EIu, GAu, n_elem)
    EAs, EIs, GAs = styvhet("stodben")
    stod_v, _ = chain(A, C, EAs, EIs, GAs, 2)
    stod_h, _ = chain(B, D, EAs, EIs, GAs, 2)
    if H1 is not None:
        EAh, EIh, GAh = styvhet("hanbjalke")
        hanbjalke, han_n = chain(H1, H2, EAh, EIh, GAh, 4,
                                 release_start=True, release_end=True)
    else:
        hanbjalke, han_n = [], []

    fr.add_support(A, ux=True, uy=True, rz=(upplag == "fast"))
    fr.add_support(B, ux=False, uy=True, rz=(upplag == "fast"))

    return fr, dict(left=A, right=B, takfot_v=C, takfot_h=D, apex=E,
                    han_v=H1, han_h=H2, x_hb=x_hb,
                    vanster=vanster, hoger=hoger, underram=underram,
                    stodben_v=stod_v, stodben_h=stod_h,
                    hanbjalke=hanbjalke,
                    vanster_noder=vn, hoger_noder=list(reversed(hn)),
                    underram_noder=un, hanbjalke_noder=han_n)
