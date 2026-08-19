"""
Barformagan hos en enskild forbindare enligt EN 1995-1-1 kap. 8.

Handboken anger fardiga varden per spik -- 0,36 kN/snitt i flansen och
0,30 kN/snitt i livet for en 2,5x50 ankarspik -- och sager samtidigt
(s. 284) att "another nail or screw can be used". For att kunna byta
forbindare pa riktigt maste kapaciteten raknas fram, inte lasas i en tabell.
Det ar vad den har modulen gor.

Alla formler har sin EC5-referens i docstringen. Enheter internt: N och mm,
alltsa f_h i MPa, M_y i Nmm, F i N. Publika funktioner som returnerar en
kraft returnerar kN, markerat i returnamnet.

Referenser:
  8.2.2      Johansens brottmoder, ekv. 8.6 (enkelsnitt) och 8.7 (dubbelsnitt)
  tab. 8.1   repeffektens andel av Johansendelen
  8.3.1.1    spikforband: ekv. 8.14 M_y,Rk, ekv. 8.15/8.16 f_h i tra,
             ekv. 8.20 f_h i plywood, ekv. 8.22 f_h i OSB och spanskiva,
             inträngningsdjup
  8.3.1.2    minsta forbindaravstand, tab. 8.2, och minsta tjocklek mot
             sprickbildning
"""

from dataclasses import dataclass, field
from math import cos, sin, sqrt


# ---------------------------------------------------------------------------
# Forbindaren
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Forbindare:
    """
    namn         beteckning
    d            diameter [mm]
    langd        total langd [mm]
    f_u          tradets draghallfasthet [MPa]. EN 14592 kraver minst 600
                 for spiktrad. Anges i tillverkarens deklaration.
    typ          "rund", "rillad" eller "kvadratisk". Styr bade M_y,Rk
                 (ekv. 8.14) och repeffektens andel (tab. 8.1).
    forborrning  True om halet forborras. Andrar f_h i tra och tar bort
                 sprickkravet i 8.3.1.2.
    F_ax_Rk      karakteristisk utdragskapacitet [N]. Default 0 = ingen
                 repeffekt raknas. Se repeffekt_andel().
    """
    namn: str
    d: float
    langd: float
    f_u: float = 600.0
    typ: str = "rund"
    forborrning: bool = False
    F_ax_Rk: float = 0.0

    def __post_init__(self):
        if self.typ not in ("rund", "rillad", "kvadratisk"):
            raise ValueError(f"okand forbindartyp: {self.typ}")
        if self.d <= 0 or self.langd <= 0:
            raise ValueError("d och langd maste vara positiva")


# ---------------------------------------------------------------------------
# Flytmoment och halkantshallfasthet
# ---------------------------------------------------------------------------

def M_y_Rk(f: Forbindare) -> float:
    """
    Karakteristiskt flytmoment [Nmm], EN 1995-1-1 ekv. 8.14.

        runda spikar              M_y,Rk = 0,3 * f_u * d^2,6
        kvadratiska och rillade   M_y,Rk = 0,45 * f_u * d^2,6
    """
    koeff = 0.3 if f.typ == "rund" else 0.45
    return koeff * f.f_u * f.d ** 2.6


def f_h_tra(rho_k: float, d: float, forborrning: bool = False) -> float:
    """
    Halkantshallfasthet i tra [MPa] for spik med d <= 8 mm.

        utan forborrning   f_h,k = 0,082 * rho_k * d^-0,3      (ekv. 8.15)
        med forborrning    f_h,k = 0,082 * (1 - 0,01d) * rho_k (ekv. 8.16)
    """
    if forborrning:
        return 0.082 * (1 - 0.01 * d) * rho_k
    return 0.082 * rho_k * d ** -0.3


def f_h_plywood(rho_k: float, d: float) -> float:
    """Halkantshallfasthet i plywood [MPa], ekv. 8.20: 0,11 * rho_k * d^-0,3."""
    return 0.11 * rho_k * d ** -0.3


def f_h_osb_spanskiva(d: float, t: float) -> float:
    """
    Halkantshallfasthet i OSB och spanskiva [MPa], ekv. 8.22:

        f_h,k = 65 * d^-0,7 * t^0,1

    Notera att den INTE beror pa densiteten utan pa skivans tjocklek t.
    """
    return 65 * d ** -0.7 * t ** 0.1


def repeffekt_andel(typ: str) -> float:
    """
    Repeffektens hogsta andel av Johansendelen, tab. 8.1.

    Andelen begransar hur mycket F_ax,Rk/4 far bidra. Ar F_ax_Rk = 0 spelar
    den ingen roll -- vilket ar default, eftersom F_ax,Rk kraver deklarerade
    utdragsparametrar enligt 8.3.2 och handboken inte raknar med repeffekt
    i sina egna exempel.
    """
    return {"rund": 0.15, "rillad": 0.25, "kvadratisk": 0.25}[typ]


# ---------------------------------------------------------------------------
# Johansens brottmoder
# ---------------------------------------------------------------------------

@dataclass
class Kapacitet:
    """
    F_v_Rk_kN    karakteristisk kapacitet PER SKJUVSNITT och forbindare [kN]
    brottmod     vilken av ekvationens rader som ar minst
    moder        alla moder i kN, for redovisning
    repeffekt_kN hur mycket repeffekten bidrog med, efter kapning mot tab 8.1
    """
    F_v_Rk_kN: float
    brottmod: str
    moder: dict = field(default_factory=dict)
    repeffekt_kN: float = 0.0

    def F_v_Rd_kN(self, k_mod: float, gamma_M: float) -> float:
        """Dimensionerande kapacitet per skjuvsnitt [kN]."""
        return self.F_v_Rk_kN * k_mod / gamma_M


def _med_repeffekt(johansen: float, f: Forbindare) -> float:
    """
    Lagger till F_ax,Rk/4 men hogst tab. 8.1:s andel av Johansendelen.
    EC5 8.2.2(2).
    """
    if f.F_ax_Rk <= 0:
        return johansen
    tillskott = min(f.F_ax_Rk / 4.0, repeffekt_andel(f.typ) * johansen)
    return johansen + tillskott


def enkelsnitt(f: Forbindare, f_h_1: float, t_1: float,
               f_h_2: float, t_2: float) -> Kapacitet:
    """
    Enkelsnitt trä/skiva mot trä/skiva, EN 1995-1-1 ekv. 8.6 rad a-f.

    Anvands for den utanpaliggande skivan mot flansen: spiken gar genom
    skivan (del 1) och in i flansen (del 2), ett skjuvsnitt.

    f_h_1, t_1   halkantshallfasthet [MPa] och tjocklek [mm] i del 1
    f_h_2, t_2   samma for del 2. For en spik i tra ar t_2
                 inträngningsdjupet, inte hela flansens tjocklek.
    """
    d, My = f.d, M_y_Rk(f)
    beta = f_h_2 / f_h_1
    tk = t_2 / t_1

    a = f_h_1 * t_1 * d
    b = f_h_2 * t_2 * d
    c = (f_h_1 * t_1 * d / (1 + beta)) * (
        sqrt(beta + 2 * beta**2 * (1 + tk + tk**2) + beta**3 * tk**2)
        - beta * (1 + tk))
    dd = 1.05 * (f_h_1 * t_1 * d / (2 + beta)) * (
        sqrt(2 * beta * (1 + beta)
             + 4 * beta * (2 + beta) * My / (f_h_1 * d * t_1**2)) - beta)
    e = 1.05 * (f_h_1 * t_2 * d / (1 + 2 * beta)) * (
        sqrt(2 * beta**2 * (1 + beta)
             + 4 * beta * (1 + 2 * beta) * My / (f_h_1 * d * t_2**2)) - beta)
    g = 1.15 * sqrt(2 * beta / (1 + beta)) * sqrt(2 * My * f_h_1 * d)

    # Repeffekten galler bara de moder dar forbindaren flyter, dvs d, e, f
    moder = {"8.6a": a, "8.6b": b, "8.6c": c,
             "8.6d": _med_repeffekt(dd, f),
             "8.6e": _med_repeffekt(e, f),
             "8.6f": _med_repeffekt(g, f)}
    return _minsta(moder, {"8.6d": dd, "8.6e": e, "8.6f": g}, f)


def dubbelsnitt(f: Forbindare, f_h_1: float, t_1: float,
                f_h_2: float, t_2: float) -> Kapacitet:
    """
    Dubbelsnitt, tre delar, EN 1995-1-1 ekv. 8.7 rad g-k.

    Anvands for livforstarkningen: spiken gar plywood - liv - plywood.
    Del 1 ar de YTTRE delarna, del 2 den MELLERSTA.

    Resultatet ar kapaciteten PER SKJUVSNITT, precis som for enkelsnitt --
    8.2.2 galler "per shear plane per fastener". Faktorn 0,5 i rad h ar just
    den som fordelar mellandelens halkantskapacitet pa de tva snitten.

    Det ar den har berakningen som avgor fragan i docs/ERRATA.md punkt 2:
    om tva skjuvsnitt far utnyttjas eller inte behover inte antas, det gar
    att rakna. Kontrollera samtidigt inträngningen med
    kontrollera_intrangning().
    """
    d, My = f.d, M_y_Rk(f)
    beta = f_h_2 / f_h_1

    g = f_h_1 * t_1 * d
    h = 0.5 * f_h_2 * t_2 * d
    j = 1.05 * (f_h_1 * t_1 * d / (2 + beta)) * (
        sqrt(2 * beta * (1 + beta)
             + 4 * beta * (2 + beta) * My / (f_h_1 * d * t_1**2)) - beta)
    k = 1.15 * sqrt(2 * beta / (1 + beta)) * sqrt(2 * My * f_h_1 * d)

    moder = {"8.7g": g, "8.7h": h,
             "8.7j": _med_repeffekt(j, f),
             "8.7k": _med_repeffekt(k, f)}
    return _minsta(moder, {"8.7j": j, "8.7k": k}, f)


def _minsta(moder: dict, utan_repeffekt: dict, f: Forbindare) -> Kapacitet:
    brottmod = min(moder, key=moder.get)
    varde = moder[brottmod]
    rep = varde - utan_repeffekt.get(brottmod, varde)
    return Kapacitet(
        F_v_Rk_kN=varde / 1000.0,
        brottmod=brottmod,
        moder={n: v / 1000.0 for n, v in moder.items()},
        repeffekt_kN=rep / 1000.0)


# ---------------------------------------------------------------------------
# Geometrikrav
# ---------------------------------------------------------------------------

def minsta_intrangning(f: Forbindare) -> float:
    """
    Minsta inträngningsdjup pa spetssidan [mm], EN 1995-1-1 8.3.1.1.

        slata spikar    8d
        ovriga spikar   6d
    """
    return (8 if f.typ == "rund" else 6) * f.d


@dataclass
class Intrangning:
    """
    intrangning  hur langt forbindaren gar in i sista delen [mm]
    krav         8d for slata spikar, 6d for ovriga [mm]
    uppfyllt     True om kravet halls, dvs om det bortre skjuvsnittet
                 far raknas med
    fel          hinder som gor att kapaciteten inte far utnyttjas
    anmarkningar praktiska papekanden som inte paverkar kapaciteten
    """
    intrangning: float
    krav: float
    uppfyllt: bool
    fel: list = field(default_factory=list)
    anmarkningar: list = field(default_factory=list)


def kontrollera_intrangning(f: Forbindare, tjocklekar: list) -> Intrangning:
    """
    Kontrollerar att forbindaren racker till de skjuvsnitt man vill utnyttja,
    EN 1995-1-1 8.3.1.1.

    tjocklekar   delarnas tjocklek i den ordning forbindaren gar igenom dem
                 [mm], t.ex. [18, 10, 18] for plywood - liv - plywood

    Det ar inträngningen i SISTA delen som avgor om det bortre skjuvsnittet
    far raknas. Att spetsen gar ut pa andra sidan ar inget hinder for
    kapaciteten, bara nagot man vill veta om pa en synlig yta.
    """
    fore = sum(tjocklekar[:-1])
    intrangning = f.langd - fore
    krav = minsta_intrangning(f)
    fel, anm = [], []

    if intrangning <= 0:
        fel.append(
            f"{f.namn} ar {f.langd:.0f} mm och naar inte ens fram till "
            f"sista delen, som borjar {fore:.0f} mm in")
    elif intrangning < krav:
        fel.append(
            f"{f.namn}: inträngning i sista delen {intrangning:.1f} mm "
            f"< kravet {krav:.1f} mm ({'8d' if f.typ == 'rund' else '6d'} "
            f"enligt 8.3.1.1). Det bortre skjuvsnittet far inte raknas.")
    elif intrangning > tjocklekar[-1]:
        anm.append(
            f"{f.namn} gar {intrangning - tjocklekar[-1]:.1f} mm ut pa "
            f"andra sidan. Kravet {krav:.1f} mm ar uppfyllt, men spetsen "
            f"sticker ut.")

    return Intrangning(intrangning=intrangning, krav=krav,
                       uppfyllt=not fel, fel=fel, anmarkningar=anm)


def minsta_avstand(f: Forbindare, alpha: float = 0.0,
                   rho_k: float = 380.0) -> dict:
    """
    Minsta forbindaravstand [mm] enligt tab. 8.2, for spik med d < 5 mm i
    tra med rho_k <= 420 kg/m3 utan forborrning.

    alpha    vinkel mellan kraft och fiberriktning [grader]

        a1   (5 + 5|cos alpha|) d   parallellt fibrerna
        a2   5d                     vinkelratt fibrerna
        a3t  (10 + 5 cos alpha) d   belastad ande
        a3c  10d                    obelastad ande
        a4t  (5 + 2 sin alpha) d    belastad kant
        a4c  5d                     obelastad kant

    Vid forborrning galler andra, mindre varden. Den grenen ar inte
    implementerad -- anropet hojer ett fel i stallet for att tysta ge
    varden for fel fall.
    """
    if f.forborrning:
        raise NotImplementedError(
            "tab. 8.2 for forborrade hal ar inte implementerad")
    if f.d >= 5.0:
        raise NotImplementedError(
            f"tab. 8.2-raden galler d < 5 mm, fick d = {f.d}")
    if rho_k > 420:
        raise NotImplementedError(
            f"tab. 8.2-raden galler rho_k <= 420, fick {rho_k}")

    from math import radians
    a = radians(alpha)
    d = f.d
    return {"a1": (5 + 5 * abs(cos(a))) * d,
            "a2": 5 * d,
            "a3t": (10 + 5 * cos(a)) * d,
            "a3c": 10 * d,
            "a4t": (5 + 2 * sin(a)) * d,
            "a4c": 5 * d}


def minsta_tjocklek_mot_sprickning(f: Forbindare, rho_k: float) -> float:
    """
    Minsta tjocklek pa tradelen for att spika utan forborrning,
    EN 1995-1-1 8.3.1.2:

        t = max( 7d ; (13d - 30) * rho_k/400 )

    Understiger tradelens tjocklek det har kravs forborrning.
    """
    return max(7 * f.d, (13 * f.d - 30) * rho_k / 400.0)


# ---------------------------------------------------------------------------
# Forskjutningsmodul
# ---------------------------------------------------------------------------

def K_ser(f: Forbindare, rho_m: float) -> float:
    """
    Forskjutningsmodul per skjuvsnitt och forbindare [N/mm],
    EN 1995-1-1 tab. 7.1:

        spik utan forborrning   K_ser = rho_m^1,5 * d^0,8 / 30
        spik med forborrning    K_ser = rho_m^1,5 * d / 23

    rho_m ar MEDELdensiteten [kg/m3], inte den karakteristiska. Har de tva
    forbundna delarna olika densitet ska rho_m = sqrt(rho_m1*rho_m2)
    anvandas (7.1(2)) -- det ar anroparens ansvar att skicka in rätt varde.
    """
    if f.forborrning:
        return rho_m ** 1.5 * f.d / 23.0
    return rho_m ** 1.5 * f.d ** 0.8 / 30.0


def K_u(f: Forbindare, rho_m: float) -> float:
    """
    Forskjutningsmodul i brottgranstillstand [N/mm], EN 1995-1-1 2.2.2(2):
    K_u = 2/3 * K_ser. Anvands nar forbandets eftergivlighet gar in i
    snittkraftsfordelningen i brottgranstillstand -- som nockens
    rotationsfjader i ramanalysen.
    """
    return 2.0 / 3.0 * K_ser(f, rho_m)


def K_rot(grupper, rho_m: float, brottgrans: bool = False) -> float:
    """
    Rotationsstyvhet for en spikgrupp som faster en styv skiva i EN stel
    del [kNm/rad]:

        K_r = sum over grupper av ( K_ser * n_snitt * I_p )

    dar I_p = sum(r_i^2) ar gruppens polara troghetsmoment [mm2]. Det ar
    samma elasticitetsteori som kapacitetsformeln F = M*r/I_p, fast for
    styvhet: varje forbindare ar en fjader K_ser pa havarmen r_i.

    OBS: for en SKARV, dar skivan faster i TVA delar som ska rotera mot
    varandra, ar det har inte svaret -- anvand K_rot_skarv().

    grupper   lista av (forbindare, n_snitt, I_p [mm2])
    """
    K = K_u if brottgrans else K_ser
    return sum(K(f, rho_m) * n_snitt * Ip for f, n_snitt, Ip in grupper) / 1e6


def K_rot_skarv_vriden(grupper, rho_m: float, alfa: float,
                       brottgrans: bool = False) -> float:
    """
    Skarvens rotationsstyvhet [kNm/rad] i nockens VERKLIGA geometri.

    Spikkoordinaterna vrids med forband.vrid_till_nock -- exakt samma
    transform som ritningen anvander -- och skivan loses som fri styv
    kropp: minimera fjadrarnas tojningsenergi over skivans tre
    frihetsgrader nar sparrarna roterar -phi/2 respektive +phi/2 kring
    fogpunkten. Varje spik sitter i sin sparre.

    Vid alfa = 0 aterfas exakt den slutna formeln K*n_snitt*I_egen/2
    (lases av test_forband_skarv). Med vaxande taklutning STIGER
    styvheten: halvornas tyngdpunkter ror sig inte langre parallellt, sa
    skivans translation kan inte avlasta bada samtidigt och en del av
    Steinertermen kommer tillbaka. For 27 graders taklutning ar
    skillnaden ca 11 %.

    grupper   lista av (forbindare, n_snitt, coords) dar coords ar de
              PLATTA koordinaterna fran spikgrupper()
    """
    import numpy as np

    from forband import vrid_till_nock

    K = K_u if brottgrans else K_ser
    phi = 1e-3
    total = 0.0
    for f, n_snitt, coords in grupper:
        k = K(f, rho_m) * n_snitt          # N/mm per spik
        A = np.zeros((3, 3))
        b = np.zeros(3)
        lagen = [(vrid_till_nock(x, y, alfa), y > 0) for x, y in coords]
        for (X, Y), hoger in lagen:
            th = phi / 2 if hoger else -phi / 2
            ur = np.array([-th * Y, th * X])        # sparrens rorelse
            B = np.array([[1.0, 0.0, -Y], [0.0, 1.0, X]])
            A += k * B.T @ B
            b += k * B.T @ ur
        d = np.linalg.solve(A, b)                   # skivans rorelse
        E = 0.0
        for (X, Y), hoger in lagen:
            th = phi / 2 if hoger else -phi / 2
            ur = np.array([-th * Y, th * X])
            B = np.array([[1.0, 0.0, -Y], [0.0, 1.0, X]])
            dl = ur - B @ d
            E += 0.5 * k * float(dl @ dl)
        total += 2.0 * E / phi ** 2
    return total / 1e6


def K_rot_skarv(halvor, rho_m: float, brottgrans: bool = False) -> float:
    """
    Rotationsstyvhet for en SKARV med genomgaende skivor [kNm/rad], dvs
    det momentstyva nockforbandet: skivan ar spikad i vanster sparre av
    forbindarna pa ena sidan fogen och i hoger sparre av de pa den andra.

        1/K_grupp = 1/(K*n_snitt*I_vanster) + 1/(K*n_snitt*I_hoger)

    dar I_vanster/I_hoger ar HALVGRUPPENS polara troghetsmoment om SIN
    EGEN tyngdpunkt. Ar halvorna lika stora blir det K*n_snitt*I_egen/2.
    Grupperna (flans, liv) sitter pa var sitt skivpar och adderas.

    halvor   lista av (forbindare, n_snitt, I_vanster, I_hoger) [mm2]

    HARLEDNING. Skivan ar en FRI styv kropp med tre frihetsgrader, hallen
    bara av spikarna. Lat sparrarna rotera -phi/2 respektive +phi/2 kring
    fogen. Halvgruppernas tyngdpunkter ligger i (0, -d) och (0, +d), och
    deras forskjutningar blir da

        (0, -d):  (-(-phi/2)*(-d), 0) = (-phi*d/2, 0)
        (0, +d):  (-(+phi/2)*(+d), 0) = (-phi*d/2, 0)

    -- BADA at samma hall. Skivan foljer helt enkelt med, translaterar
    -phi*d/2 och roterar INTE. Varje halvgrupp ser da en REN rotation
    phi/2 kring sin egen tyngdpunkt, och translationsbidraget n*d^2
    faller bort. Momentet som gar genom skivan blir

        M = K*n_snitt*I_egen*(phi/2)   =>   K = M/phi = K*n*I_egen/2.

    VARNING TILL DEN SOM VILL "RATTA" DET HAR: att lagga till Steiners
    term n*d^2 ar frestande men fel -- det svarar mot en skiva som HALLS
    FAST mot translation, vilket ingenting gor. Den varianten gav
    K_rot/4 = 538 kNm/rad mot rattens 355 for projektfilens spikning,
    dvs 1,5 ganger for styvt, och det underskattade bade faltmoment och
    nedbojning. En numerisk energiminimering over skivans tre
    frihetsgrader reproducerar formeln ovan pa decimalen -- se
    test_forband_skarv.py.
    """
    K = K_u if brottgrans else K_ser
    total = 0.0
    for f, n_snitt, I_v, I_h in halvor:
        k = K(f, rho_m) * n_snitt
        if I_v <= 0 or I_h <= 0:
            continue
        total += 1.0 / (1.0 / (k * I_v) + 1.0 / (k * I_h))
    return total / 1e6
