"""
Upplagskapacitet for lattbalken enligt ETA 12/0018 avsn. 1.2.3.

Metoden ar ETA:ns egen, inte EC5:s tryck-vinkelratt-fibrerna: lattbalkens
brottmoder vid upplag ar livbuckling och flansssprickning, och ETA:n ger
en provningsbaserad formel med parametrar ur tab. 6-9.

    utan forstarkning, MED punktlast over stodet    (ekv. 3)
        F_k = (L1/45)^0,5 * a * k_A * k_6
    med forstarkning, UTAN punktlast over stodet    (ekv. 4)
        F_k = (L1/45)^0,5 * a * k_B * k_7
    utan forstarkning, utan punktlast: k_A = 1,0
    med forstarkning, med punktlast:   k_B = 1,0

    a for andupplag = a_bas + delta_a,  delta_a = 4y/(h/2)   (ekv. 5)
    y = balkens utstick utanfor stodet. y > h -> rakna som mittstod.

Effektiv upplagslangd: andupplag L1 <= 150 mm, mittstod L1 <= 200 mm --
men bara 150 mm nar h <= 220 mm (ETA fotnot 3 till avsn. 1.2.3, s. 9).
Minsta tillatna upplagslangd ar 45 mm (annex 3). ETA:ns fotnot: kapaciteten
far aldrig overstiga tvarkraftskapaciteten -- F_d <= V_d vid andupplag och
F_d <= 2*V_d vid mittstod.

Tabellerna 7 och 8 (k_A, k_B) interpoleras linjart i bade L1 och h, med
linjar EXTRAPOLERING i L1-anden dar tabellen saknar kolumn -- det ar sa
ETA:ns egna tab. 13/14 ar framraknade, vilket verifieras i
tests/test_eta_upplag.py mot ett urval av de ca 200 tryckta vardena.

k_mod: ETA tab. 17:s fotnot -- for upplag MED punktlast UTAN forstarkning
vid h >= 250 (andupplag) resp. h >= 300 (mittstod) galler TVARKRAFTENS
k_mod (som beror pa livmaterialet). I ovriga fall bojningens.
"""

from dataclasses import dataclass, field

import material


def _interp(x, xs, ys):
    """Linjar interpolation med linjar extrapolering utanfor tabellen."""
    if x <= xs[0]:
        i = 0
    elif x >= xs[-1]:
        i = len(xs) - 2
    else:
        i = next(k for k in range(len(xs) - 1) if xs[k + 1] >= x)
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + t * (ys[i + 1] - ys[i])


def _tabell(tab, h, L1, lage):
    """Slar upp k_A eller k_B ur [upplag]-blocket, interpolerat i h och L1."""
    L1_kol = tab["L1_and"] if lage == "and" else tab["L1_mitt"]
    rader = tab["and_upplag"] if lage == "and" else tab["mitt_upplag"]
    h_rader = tab["h_rader"]
    # interpolera i L1 pa varje h-rad, sedan i h (klampat till tabellen --
    # utanfor h-omradet finns inga deklarerade varden att extrapolera till)
    per_h = [_interp(L1, L1_kol, rad) for rad in rader]
    h_klamp = min(max(h, h_rader[0]), h_rader[-1])
    return _interp(h_klamp, h_rader, per_h)


def k_A(h, L1, lage):
    """
    ETA tab. 7. Galler UTAN forstarkning MED punktlast, annars 1,0.

    k_A ar en REDUKTIONSFAKTOR och kapas vid 1,0: for mittstod borjar
    tabellen vid L1 = 70, och en linjar extrapolering nedat skulle ge
    varden over 1,0 -- men ETA:ns egen tab. 13 visar 14,0 = a rakt av vid
    L1 = 45 for alla hojder, dvs k_A = 1,0. k_B ar tvartom en
    FORHOJNINGSFAKTOR och extrapoleras (sa traffas tab. 14:s 18,2).
    """
    return min(1.0, _tabell(material.BALKAR_DATA["upplag"]["k_A"], h, L1,
                            lage))


def k_B(h, L1, lage):
    """ETA tab. 8. Galler MED forstarkning UTAN punktlast, annars 1,0."""
    return _tabell(material.BALKAR_DATA["upplag"]["k_B"], h, min(L1, 150),
                   lage)


def k_6(h):
    """ETA tab. 9. Andupplag utan forstarkning, alla balktyper."""
    d = material.BALKAR_DATA["upplag"]["k_6_k_7"]
    if h < d["h_rader"][0]:
        return d["k_6_under_400"]
    return _interp(h, d["h_rader"], d["k_6"])


def k_7(h, serie):
    """ETA tab. 9. Bara forstarkta HB-balkar utan punktlast, annars 1,0."""
    if serie != "HB":
        return 1.0
    d = material.BALKAR_DATA["upplag"]["k_6_k_7"]
    if h < d["h_rader"][0]:
        return d["k_7_under_400"]
    return _interp(h, d["h_rader"], d["k_7"])


@dataclass
class Upplagskapacitet:
    F_k: float                  # kN, karakteristisk
    F_Rd: float                 # kN, dimensionerande (inkl V_d-taket)
    F_Rd_tryck: float           # kN, fore V_d-taket
    V_Rd_tak: float             # kN, tvarkraftstaket (V_d resp 2V_d)
    lage: str                   # "and" | "mitt"
    formel: str
    k_mod: float
    k_mod_rad: str              # "bojning" | "tvarkraft"
    detaljer: dict = field(default_factory=dict)
    anmarkningar: list = field(default_factory=list)


def kapacitet(balk, L1, lage="and", forstarkning=False, punktlast=False,
              y=0.0, L2=None, klimatklass=1, varaktighet="medel",
              gamma_M=1.30) -> Upplagskapacitet:
    """
    Dimensionerande upplagskapacitet for en balk.

    L1     upplagslangd [mm]
    lage   "and" for andupplag, "mitt" for mittstod/innerupplag
    y      utstick utanfor stodet vid andupplag [mm]
    L2     upplagslangd pa motstaende sida [mm]; ar L2 < L1 anvands L2
           (ETA:s fotnot 2)
    """
    anm = []
    if L1 < 45.0:
        anm.append(f"L1 = {L1:.0f} mm < minsta tillåtna 45 mm (annex 3)")
    if L2 is not None and L2 < L1:
        anm.append(f"L2 = {L2:.0f} mm < L1 används som upplagslängd "
                   f"(fotnot 2)")
        L1 = L2
    if lage == "and" and y > balk.h:
        anm.append(f"utsticket y = {y:.0f} mm > h: räknas som mittstöd")
        lage = "mitt"

    # ETA s. 9: "For end support: L1 = min(L1 and 150 mm). For mid
    # support and inner bearing: L1 = min(L1 and 200 mm)" med fotnot 3:
    # "For situations when h <= 220 mm, bearing capacity shall be
    # calculated for L1 = 150 mm." Den grundare balken far alltsa samma
    # tak som andupplaget aven vid mittstod.
    if lage == "and":
        L1e = min(L1, 150.0)
    else:
        L1e = min(L1, 150.0 if balk.h <= 220.0 else 200.0)
    a_tab = material.BALKAR_DATA["upplag"]["a"][balk.serie]

    if lage == "and":
        delta_a = 4.0 * y / (balk.h / 2.0)
        a = a_tab["and_bas"] + delta_a
    else:
        a = a_tab["mitt"]

    rot = (L1e / 45.0) ** 0.5
    if punktlast and not forstarkning:
        kA, kB = k_A(balk.h, L1e, lage), 1.0
        k6 = k_6(balk.h) if lage == "and" else 1.0
        k7 = 1.0
        formel = "ekv. 3: (L1/45)^0.5 * a * k_A * k_6"
    elif forstarkning and not punktlast:
        kA, k6 = 1.0, 1.0
        kB = _tabell(material.BALKAR_DATA["upplag"]["k_B"], balk.h,
                     min(L1e, 150.0), lage)
        k7 = k_7(balk.h, balk.serie)
        formel = "ekv. 4: (L1/45)^0.5 * a * k_B * k_7"
    elif forstarkning and punktlast:
        kA, kB, k6, k7 = 1.0, 1.0, 1.0, 1.0
        formel = "(L1/45)^0.5 * a  (k_B = 1 med punktlast, k_6 = 1 med " \
                 "förstärkning)"
    else:
        kA, kB, k7 = 1.0, 1.0, 1.0
        k6 = k_6(balk.h) if lage == "and" else 1.0
        formel = "(L1/45)^0.5 * a * k_6  (k_A = 1 utan punktlast)"

    F_k = rot * a * kA * kB * k6 * k7

    # k_mod: tab. 17:s fotnot styr vilken rad som galler
    tvarkraftsrad = (punktlast and not forstarkning
                     and balk.h >= (250 if lage == "and" else 300))
    if tvarkraftsrad:
        kmod = material.k_mod_tvarkraft(balk.liv, klimatklass, varaktighet)
        rad = "tvarkraft"
    else:
        kmod = material.k_mod_bojning(klimatklass, varaktighet)
        rad = "bojning"

    F_Rd_tryck = F_k * kmod / gamma_M

    # Tvarkraftstaket, ETA:s fotnot till ekv. 3/4
    kmod_v = material.k_mod_tvarkraft(balk.liv, klimatklass, varaktighet)
    V_Rd = balk.V_k * kmod_v / gamma_M
    tak = V_Rd if lage == "and" else 2.0 * V_Rd
    F_Rd = min(F_Rd_tryck, tak)
    if F_Rd < F_Rd_tryck:
        anm.append(f"tvarkraften begransar: F_Rd = "
                   f"{'V_Rd' if lage == 'and' else '2*V_Rd'} = {tak:.1f} kN "
                   f"< upplagstrycket {F_Rd_tryck:.1f} kN")

    return Upplagskapacitet(
        F_k=F_k, F_Rd=F_Rd, F_Rd_tryck=F_Rd_tryck, V_Rd_tak=tak, lage=lage,
        formel=formel, k_mod=kmod, k_mod_rad=rad,
        detaljer=dict(L1_eff=L1e, a=a, k_A=kA, k_B=kB, k_6=k6, k_7=k7),
        anmarkningar=anm)
