"""
Momentstyvt skivforband i lattbalk.

Metod: Masonite Beams "The I-joist Handbook" (2022) avsn. 5.3.4.1,
"Moment rigid upper frame corner". Handboken anger att samma berakningsgang
kan tillampas pa de flesta knutpunkter i en takstol - inklusive nocken,
som i handbokens egna takstolstyper alltid ar ledad.

Uppbyggnad:
  - livforstarkning av plywood pa bada sidor om livet, genomgaende over foget
  - utanpaliggande skiva over flansarna, genomgaende over foget
  - bada skivorna spikas till respektive underlag

Kapacitet:
  M_Rd = min( sum M_plywood ; sum M_forbindargrupp )
  N_Rd = sum F_i * n_i
  Kontroll: M_Ed/M_Rd + N_Ed/N_Rd <= 1.0
"""

from dataclasses import dataclass, field
from math import sqrt


# ---------------------------------------------------------------------------
# Forbindargrupp
# ---------------------------------------------------------------------------

class Forbindargrupp:
    """
    Kapacitet enligt elasticitetsteori (handbokens grundformel):
        F = M*r/Ip + N/n     ->     M_Rd = F*Ip/r,   N_Rd = F*n

    F_plane   dimensionerande skjuvkapacitet PER SKJUVSNITT [kN]
    n_planes  antal skjuvsnitt per forbindare
              1 = utanpaliggande skiva -> flans (spik gar plywood -> tra)
              2 = livforstarkning (spik gar plywood -> liv -> plywood)

    OBS: handboken ar inte konsekvent har, se docs/ERRATA.md. Default i den
    har modulen ar 1 skjuvsnitt, vilket ar det konservativa valet.
    """

    def __init__(self, namn, F_plane, n_planes=1, coords=None,
                 n=None, Ip=None, r=None):
        self.namn = namn
        self.F_plane = F_plane
        self.n_planes = n_planes
        if coords is not None:
            self.coords = list(coords)
            self.n = len(self.coords)
            self.Ip = sum(x*x + y*y for x, y in self.coords)
            self.r = max(sqrt(x*x + y*y) for x, y in self.coords)
        else:
            self.coords = None
            self.n, self.Ip, self.r = n, Ip, r

    @property
    def F(self):
        return self.F_plane * self.n_planes

    @property
    def M_Rd(self):
        return self.F * self.Ip / self.r / 1000.0      # kNm

    @property
    def N_Rd(self):
        return self.F * self.n                         # kN

    def kraft(self, M_i, N_i, V_i=0.0):
        """Kraft pa varst belastad forbindare for gruppens lastandel [kN]."""
        return M_i * 1e3 * self.r / self.Ip + sqrt(N_i**2 + V_i**2) / self.n

    # -- skarv: gruppen delad vid fogen -----------------------------------

    def halvdata(self):
        """
        (n_halv, Ip_egen, r_egen, d) for halvgruppen pa EN sida av fogen.

        Fogen ligger vid y = 0 (y ar langs balken). Ip_egen och r_egen
        raknas om HALVGRUPPENS EGEN tyngdpunkt, och d ar dess avstand
        till fogen. Ar halvorna olika stora returneras den ogynnsamma
        (storst kraft per enhet moment, dvs storst r_egen/Ip_egen).

        Behovs for skarvkontrollen: skar man loss ena sparren hanger den
        BARA i spikarna pa sin egen sida av fogen, sa hela M, N och V
        maste passera den halvan. Se docs/ERRATA.md punkt 7.
        """
        if self.coords is None:
            return None
        varst = None
        for tecken in (-1, 1):
            halv = [(x, y) for x, y in self.coords if tecken * y > 0]
            if not halv:
                continue
            xm = sum(x for x, _ in halv) / len(halv)
            ym = sum(y for _, y in halv) / len(halv)
            Ip = sum((x - xm) ** 2 + (y - ym) ** 2 for x, y in halv)
            r = max(sqrt((x - xm) ** 2 + (y - ym) ** 2) for x, y in halv)
            kandidat = (len(halv), Ip, r, abs(ym))
            if varst is None or r / Ip > varst[2] / varst[1]:
                varst = kandidat
        return varst

    @property
    def M_Rd_skarv(self):
        """Momentkapacitet raknad per halvgrupp [kNm]. Exklusive V*d,
        som ar lastberoende och laggs pa i kraft_skarv()."""
        h = self.halvdata()
        if h is None:
            return self.M_Rd
        _, Ip, r, _ = h
        return self.F * Ip / r / 1000.0

    @property
    def N_Rd_skarv(self):
        h = self.halvdata()
        return self.F * (h[0] if h else self.n)

    def kraft_skarv(self, M_i, N_i, V_i=0.0):
        """
        Kraft pa varst belastad forbindare i halvgruppen [kN].

        Snittkrafterna flyttas fran fogen till halvgruppens tyngdpunkt,
        vilket lagger till excentricitetsmomentet V*d -- samma steg som
        handbokens 5.3.7 gor for den ledade nocken.
        """
        h = self.halvdata()
        if h is None:
            return self.kraft(M_i, N_i, V_i)
        n_halv, Ip, r, d = h
        M_tot = abs(M_i) + abs(V_i) * d / 1000.0        # kNm
        return M_tot * 1e3 * r / Ip + sqrt(N_i**2 + V_i**2) / n_halv


def rader_langs_balken(x_offset, rader, s, alfa, kant, forskjut=0.0,
                       bas_andel=0.5, ankare=None):
    """
    y-lagen (langs balken fran fogen) for en spikkolonn pa
    tvarsavstandet x_offset [mm] fran balkaxeln.

    Sparrarna kapas i en LODRAT stotfog. En spik i platta koordinater
    (x, y) ligger pa det vinkelrata avstandet

        X = y*cos(alfa) + x*sin(alfa)

    fran fogplanet. Kravet X >= kant (kantavstand mot kapad ande) ger

        y_start = max(s/2 + forskjut, (kant - x*sin(alfa))/cos(alfa))

    Kolonner UNDER balkaxeln (x < 0) borjar alltsa langre fran fogen --
    med platt placering hamnar deras forsta spikar bokstavligen inne i
    motstaende sparre. forskjut ar zigzag-forskjutningen s/2.

    Vid alfa = 0 aterfas den platta placeringen exakt, sa handbokens
    exempel (som raknar platt) reproduceras med taklutning 0.
    """
    from math import ceil, cos, sin
    # bas_andel: var rastret borjar. 0.5 = handbokens platta bild
    # (forsta raden s/2 fran fogen; 5.3.4.1/5.3.7 reproduceras sa).
    # `ankare` [mm langs balken] later i stallet en rasterlinje ga
    # EXAKT genom det avstandet: rastret blir (ankare mod s) + n*s.
    # Anvands for flansvinkeln (h/2)*tan(alfa) -- referenslinjen genom
    # vinkeln mellan undre flansarna (anvandarbeslut 2026-08-19), en
    # punkt man kan kanna pa den fardiga takstolen.
    if ankare is not None:
        bas = (ankare % s) + forskjut
    else:
        bas = bas_andel * s + forskjut
    krav = (kant - x_offset * sin(alfa)) / cos(alfa)
    # RUTNATSSNAPPNING (2026-08-19, anvandarbeslut): starten rundas UPP
    # till narmaste rasterlage bas + n*s i stallet for det kontinuerliga
    # kantkravet. Da ligger HELA spikbilden pa ett ritbart rutnat --
    # tvarlinjer fran fogen, kritlinjer fran skivkanten, spik i
    # korsningarna -- och utsattningen blir mojlig utan tumstocksmatt
    # som 48,0/60,7 mm. Konservativt: spiken flyttar FRAN fogen, aldrig
    # mot den, sa kantkravet ar alltid uppfyllt.
    steg = max(0, ceil((krav - bas) / s - 1e-9))
    y0 = bas + steg * s
    return [y0 + i * s for i in range(rader)]




def vrid_till_nock(x, y, alfa):
    """
    Platt spikkoordinat -> lage i nockens verkliga geometri [mm].

    Berakningen och ritningen anvander samma platta koordinater: x TVARS
    balken, y LANGS balken raknat fran fogen (negativ y = vanster
    sparre). I verkligheten moter sparrarna varandra med taklutningen
    alfa [rad]; har vrids varje halva till sin sparre, kring fogpunkten.

    Det har ar DEN gemensamma transformen: ritningen ritar med den och
    K_rot_skarv_vriden raknar med den, sa bild och siffra kommer ur
    exakt samma geometri.
    """
    from math import cos, sin
    hoger = y > 0
    ax, ay = (cos(alfa), -sin(alfa)) if hoger else (-cos(alfa), -sin(alfa))
    nx, ny = (sin(alfa), cos(alfa)) if hoger else (-sin(alfa), cos(alfa))
    d = abs(y)
    return (d * ax + x * nx, d * ay + x * ny)


def rutnat(x_pos, y_pos, n_sidor=2):
    """
    Forbindarkoordinater [mm] relativt gruppens tyngdpunkt.

    n_sidor DUBBLERAR listan och betyder spik slagna FRAN BADA SIDOR --
    handbokens egen rakning: exempel 5.3.4.1 har "14 nails per flange
    and side" och summerar n_flange = 4*14 = 56, vilket ar precis
    rutnat([-126.5, 126.5], sym(12.5, 25, 7), n_sidor=2).

    Det ar en ANNAN sak an antalet skjuvsnitt per spik (n_planes), som
    beror pa vad spiken gar igenom: 1 for skiva -> flans (spiken stannar
    i flansen), 2 for skiva -> liv -> skiva nar intrangningen racker
    (8.3.1.1). De tva faktorerna ar oberoende och ska bada med -- se
    test_forband_konvention.py.
    """
    return [(x, y) for x in x_pos for y in y_pos] * n_sidor


def sym(start, steg, antal):
    """Symmetriska koordinater +/-(start + i*steg)."""
    v = [start + i*steg for i in range(antal)]
    return [-x for x in reversed(v)] + v


def kontrollera_avstand(coords, a1, a2, kant_min=None):
    """
    Grov kontroll av minsta forbindaravstand enligt EN 1995-1-1 8.3.1.2.
    Returnerar lista med overtradelser.
    """
    fel = []
    unika = sorted(set(coords))
    for i, (x1, y1) in enumerate(unika):
        for x2, y2 in unika[i+1:]:
            dx, dy = abs(x2-x1), abs(y2-y1)
            if dy < 1e-9 and dx < a1 - 1e-9:
                fel.append(f"c/c {dx:.1f} mm < a1 = {a1} mm")
            if dx < 1e-9 and dy < a2 - 1e-9:
                fel.append(f"c/c {dy:.1f} mm < a2 = {a2} mm")
    return sorted(set(fel))


# ---------------------------------------------------------------------------
# Plywoodskiva
# ---------------------------------------------------------------------------

@dataclass
class Skiva:
    namn: str
    t: float          # tjocklek per skiva [mm]
    h: float          # skivhojd [mm]
    n_skivor: int
    f_m_k: float      # MPa
    k_mod: float
    gamma_M: float

    @property
    def W(self):
        return self.n_skivor * self.t * self.h**2 / 6.0     # mm3

    @property
    def M_k(self):
        return self.W * self.f_m_k / 1e6                    # kNm

    @property
    def M_d(self):
        return self.M_k * self.k_mod / self.gamma_M


def skjuvkontroll_skiva(t_PL, l_snitt, f_v_k, k_mod, gamma_M,
                        n_skivor=2, k_cr=1.0):
    """
    Skjuvkapacitet i skivans snitt langs flansen (handbokens 5.3.4.2).
    V_Rd = n * k_cr * t * l * f_v_k / 1.5 * k_mod/gamma_M   [kN]
    Faktorn 1.5 ar den paraboliska skjuvspanningsfordelningen.
    """
    return (n_skivor * k_cr * t_PL * l_snitt * f_v_k / 1.5
            * k_mod / gamma_M / 1000.0)


# ---------------------------------------------------------------------------
# Ledat nockforband, handboken 5.3.7
# ---------------------------------------------------------------------------

@dataclass
class LedadNock:
    """
    grupp        spikgruppen PA EN SIDA av fogen, koordinater relativt sin
                 egen tyngdpunkt
    e            havarm fran gruppens tyngdpunkt till fogen [mm]
    M            excentricitetsmomentet V*e [kNm]
    F            kraft pa varst belastad forbindare [kN]
    F_Rd         kapacitet per forbindare [kN]
    u_forbindare F/F_Rd
    V_skiva_Rd   skivornas skjuvkapacitet i fogsnittet [kN]
    u_skiva_skjuv, u_skiva_moment  utnyttjanden for skivorna
    """
    grupp: Forbindargrupp
    e: float
    M: float
    F: float
    F_Rd: float
    u_forbindare: float
    V_skiva_Rd: float
    u_skiva_skjuv: float
    u_skiva_moment: float
    metodnot: str = ""
    varningar: list = field(default_factory=list)   # t.ex. spik utanfor skivan

    @property
    def utnyttjande(self):
        return max(self.u_forbindare, self.u_skiva_skjuv,
                   self.u_skiva_moment)


def ledad_nock(N, V, kolumner, rader, s, F_Rd_per_snitt, n_snitt,
               t_skiva, h_skiva, f_t_skiva, f_v_skiva, k_mod, gamma_M,
               taklutning_grader=0.0, kant_ande=0.0, forskjut_sida=0.0,
               bas_andel=0.5, ankare=None):
    """
    Ledat nockforband enligt handboken 5.3.7: skivor pa bada sidor om
    livet, genomgaende over fogen, spikade direkt mot livet. Forbandet
    overfor N och V men inget moment.

    Nar tvarkraften flyttas fran ena sparrens spikgrupp till den andra
    uppstar ett moment av excentriciteten: M = V*e, dar e ar avstandet
    fran gruppens tyngdpunkt till fogen (handboken 5.3.7.1). Kraften pa
    varst belastad spik raknas med elasticitetsteorin.

    METODVAL: handbokens exempel satter F = M*r/Ip + N/n och utelamnar
    tvarkraftens direkta andel V/n. Har raknas F = M*r/Ip +
    sqrt(N^2+V^2)/n, vilket ar det konsekventa uttrycket (samma som
    5.3.5/5.3.6 anvander) och strangare an handbokens. Det redovisas i
    metodnoten.

    kolumner, rader   spikgruppens rutnat PA EN SIDA av fogen, per
                      skivsida. SAMMA axlar som berakning.spikgrupper:
                      KOLUMNER tvars balken (begransas av skivhojden),
                      RADER langs balken ut fran fogen -- det ar radernas
                      avstand som ger excentriciteten e.
    s                 c/c [mm]
    n_snitt           skjuvsnitt per spik (2 for skiva-liv-skiva om
                      intrangningen racker, se 8.3.1.1)
    h_skiva           skivans hojd i fogsnittet [mm] (= fria livhojden nar
                      skivan sitter pa livet)
    f_t_skiva         skivans draghallfasthet i planet [MPa] for
                      momentkontrollen av skivan
    """
    # Gruppen pa en sida av fogen, pa BADA skivsidorna. Axlarna foljer
    # berakning.spikgrupper: x TVARS balken (skivhojdens led), y LANGS
    # balken ut fran fogen. Det ar y-avstanden som ger excentriciteten,
    # for tvarkraften flyttas langs balken fran ena gruppen till den
    # andra. Forr lag kolumnerna i y och raderna i x, sa samma
    # konfiguration gav TRANSPONERADE spikbilder i de tva nocktyperna --
    # och --jamfor stallde da olika forband mot varandra.
    # Samma stotfogsplacering som den momentstyva vagen
    # (rader_langs_balken): forsta raden per kolonn laggs sa att
    # kantavstandet mot den lodrata kapade anden halls. Med
    # taklutning 0 och kant_ande 0 aterfas handbokens platta bild
    # (5.3.7-exemplets I_p backraknas sa i testerna).
    from math import radians as _rad
    alfa_ = _rad(taklutning_grader)
    # forskjut_sida [mm]: sida -Y laggs sa langt FRAN fogen relativt
    # sida +Y, sa att genomgaende spik fran motstaende sidor inte
    # kolliderar. 0 = spegelplacerat (handbokens platta bild).
    sida_a, sida_b = [], []
    for x in sym(s / 2, s, kolumner):
        for y in rader_langs_balken(x, rader, s, alfa_, kant_ande,
                                    bas_andel=bas_andel, ankare=ankare):
            # sida B = sida A + forskjut som REN addition --
            # rader_langs_balkens klampning far inte nolla den
            sida_a.append((x, y))
            sida_b.append((x, y + forskjut_sida))
    par = sida_a + sida_b
    e = sum(y for _, y in par) / len(par)
    coords = [(x, y - e) for x, y in par]

    F_per_spik = F_Rd_per_snitt * n_snitt
    grupp = Forbindargrupp("Ledad nock, en sida", F_Rd_per_snitt, n_snitt,
                           coords=coords)
    grupp.sidor = ([(x, y - e) for x, y in sida_a],
                   [(x, y - e) for x, y in sida_b])
    ytterst = max(abs(x) for x, _ in coords)
    varningar = ([f"Ledad nock: yttersta förbindaren ligger {ytterst:.0f} mm "
                  f"från mittlinjen men skivan är {h_skiva:.0f} mm hög "
                  f"(+/-{h_skiva / 2:.0f} mm). Förbindare utanför skivan "
                  f"får inte räknas i I_p eller n."]
                 if ytterst > h_skiva / 2.0 + 1e-9 else [])

    M = abs(V) * e / 1000.0                     # kNm
    F = grupp.kraft(M, abs(N), abs(V))
    u_forb = F / F_per_spik

    # Skivorna i fogsnittet: skjuvning av resultanten och bojning av
    # excentricitetsmomentet. Tva skivor (en per sida om livet).
    V_res = sqrt(N * N + V * V)
    V_Rd = skjuvkontroll_skiva(t_skiva, h_skiva, f_v_skiva, k_mod, gamma_M,
                               n_skivor=2)
    W = 2 * t_skiva * h_skiva ** 2 / 6.0
    M_Rd_skiva = W * f_t_skiva / 1e6 * k_mod / gamma_M

    return LedadNock(
        grupp=grupp, e=e, M=M, F=F, F_Rd=F_per_spik,
        u_forbindare=u_forb,
        V_skiva_Rd=V_Rd, u_skiva_skjuv=V_res / V_Rd,
        u_skiva_moment=M / M_Rd_skiva,
        varningar=varningar,
        metodnot="F = M*r/Ip + sqrt(N^2+V^2)/n -- strängare än handbokens "
                 "5.3.7 som utelämnar V/n. Skivans momentkontroll använder "
                 "draghållfastheten i planet.")


# ---------------------------------------------------------------------------
# Samlad kontroll
# ---------------------------------------------------------------------------

@dataclass
class Resultat:
    M_Rd: float
    N_Rd: float
    M_plywood: float
    M_forbindare: float
    dimensionerande: str
    utnyttjande: float          # handbokens egen: |M|/M_Rd + N/N_Rd
    per_grupp: dict
    skarv: bool = False         # True = halvgruppsmetoden galler
    u_handbok: float = 0.0      # interaktionen, handbokens vag
    u_handbok_totalt: float = 0.0   # inkl. gruppkontrollerna
    u_skarv_totalt: float = 0.0     # samma fall raknat per halvgrupp

    @property
    def utnyttjande_totalt(self):
        """
        Det tal som avgor om forbandet haller: det STORSTA av handbokens
        interaktion och gruppernas egna kontroller.

        Handbokens formel (5.3.4.1 s. 290) utelamnar TVARKRAFTEN, men
        varje forbindare bar sqrt(N^2 + V^2)/n vid sidan av M*r/Ip --
        det raknas redan i per_grupp. Utan den har maxen kunde
        programmet redovisa 0,982 OK samtidigt som dess egen
        gruppkontroll sa 1,011 EJ OK. `utnyttjande` ar kvar orord sa att
        jamforelsen mot handbokens exempel gar att gora rakt av.
        """
        return max([self.utnyttjande]
                   + [d["u"] for d in self.per_grupp.values()])


def kontrollera(skivor, grupper, M_Ed, N_Ed, V_Ed=0.0, N_kontakt=0.0,
                skarv=False):
    """
    skarv=False  handbokens metod (5.3.4.1): HELA spikbilden som en grupp
                 om fogens mitt. Behalls sa att exemplet gar att
                 reproducera rakt av.
    skarv=True   varje HALVGRUPP kontrolleras ensam, med snittkrafterna
                 flyttade till dess tyngdpunkt (vilket lagger till V*d).
                 Det ar den elastiska losningen for en skarv och ger
                 2-2,5 ganger storre spikkraft. Se docs/ERRATA.md punkt 7.
    """
    M_pl = sum(s.M_d for s in skivor)
    N_eff = max(N_Ed - N_kontakt, 0.0)

    def rakna(per_halvgrupp):
        M_fb = sum(g.M_Rd_skarv if per_halvgrupp else g.M_Rd for g in grupper)
        N_Rd = sum(g.N_Rd_skarv if per_halvgrupp else g.N_Rd for g in grupper)
        u = abs(M_Ed) / min(M_pl, M_fb) + N_eff / N_Rd
        pg = {}
        for g in grupper:
            M_g = g.M_Rd_skarv if per_halvgrupp else g.M_Rd
            N_g = g.N_Rd_skarv if per_halvgrupp else g.N_Rd
            M_i = abs(M_Ed) * M_g / M_fb
            N_i = N_eff * N_g / N_Rd
            V_i = abs(V_Ed) * N_g / N_Rd
            f = (g.kraft_skarv(M_i, N_i, V_i) if per_halvgrupp
                 else g.kraft(M_i, N_i, V_i))
            pg[g.namn] = dict(M=M_i, N=N_i, V=V_i, F=f, u=f / g.F)
        return M_fb, N_Rd, u, pg

    # Bada vagarna raknas ALLTID, sa att skillnaden syns oavsett val.
    M_fb_hb, N_Rd_hb, u_hb, pg_hb = rakna(False)
    M_fb_sk, N_Rd_sk, u_sk, pg_sk = rakna(True)

    M_fb, N_Rd, u, per_grupp = ((M_fb_sk, N_Rd_sk, u_sk, pg_sk) if skarv
                                else (M_fb_hb, N_Rd_hb, u_hb, pg_hb))
    M_Rd = min(M_pl, M_fb)
    dim = "plywood" if M_pl < M_fb else "forbindare"

    return Resultat(M_Rd, N_Rd, M_pl, M_fb, dim, u, per_grupp, skarv=skarv,
                    u_handbok=u_hb,
                    u_handbok_totalt=max([u_hb] + [d["u"] for d in
                                                   pg_hb.values()]),
                    u_skarv_totalt=max([u_sk] + [d["u"] for d in
                                                 pg_sk.values()]))


def rapport(titel, skivor, grupper, res, M_Ed, N_Ed, V_Ed=0.0):
    rader = ["=" * 72, titel, "=" * 72, "", "PLYWOOD"]
    for s in skivor:
        rader.append(f"  {s.namn:<28} {s.n_skivor}x{s.t:.0f} mm, h={s.h:.0f} mm"
                     f"   M_d = {s.M_d:6.2f} kNm")
    rader.append(f"  {'summa':<28} {res.M_plywood:.2f} kNm")
    rader += ["", "FÖRBINDARGRUPPER"]
    for g in grupper:
        rader.append(f"  {g.namn:<28} n={g.n:4d}  F={g.F:.3f} kN  "
                     f"Ip={g.Ip:.3e} mm2  r={g.r:.1f} mm")
        rader.append(f"  {'':<28} M_Rd={g.M_Rd:6.2f} kNm  N_Rd={g.N_Rd:6.2f} kN")
    rader.append(f"  {'summa':<28} M_Rd={res.M_forbindare:.2f} kNm  "
                 f"N_Rd={res.N_Rd:.2f} kN")
    rader += ["", "KAPACITET",
              f"  M_Rd = min({res.M_plywood:.2f} ; {res.M_forbindare:.2f}) = "
              f"{res.M_Rd:.2f} kNm   ({res.dimensionerande} dimensionerar)",
              f"  N_Rd = {res.N_Rd:.2f} kN", "", "KONTROLL",
              f"  M_Ed = {M_Ed:.2f} kNm   N_Ed = {N_Ed:.2f} kN   "
              f"V_Ed = {V_Ed:.2f} kN",
              f"  M/M_Rd + N/N_Rd = {res.utnyttjande:.3f}   "
              f"{'OK' if res.utnyttjande <= 1.0 else '<< EJ OK >>'}"
              + (f"   (per halvgrupp, ERRATA punkt 7)" if res.skarv
                 else "   (handbokens formel, utan V)"),
              *([f"  Handbokens metod (hela spikbilden om fogen) hade "
                 f"gett {res.u_handbok:.3f} -- se docs/ERRATA.md punkt 7."]
                if res.skarv else []),
              f"  DIMENSIONERANDE = {res.utnyttjande_totalt:.3f}   "
              f"{'OK' if res.utnyttjande_totalt <= 1.0 else '<< EJ OK >>'}"
              f"   (största av interaktionen och gruppkontrollerna)", ""]
    for namn, d in res.per_grupp.items():
        rader.append(f"  {namn:<28} F = {d['F']:.3f} kN  utnyttjande "
                     f"{d['u']:.3f}  {'OK' if d['u'] <= 1.0 else '<< EJ OK >>'}")
    return "\n".join(rader)
