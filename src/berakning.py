"""
Hela kedjan laster -> kombinationer -> ramanalys -> kontroller, samlad pa
ett stalle.

Bade run.py och app.py anropar kor() och far tillbaka samma Resultat. All
ingenjorslogik bor har eller djupare ner i src/. Granssnitten far bara lasa
ur resultatet och stalla upp det -- ingen formel ovanfor den har filen.

Vad som kontrolleras:
  - balken i brottgranstillstand langs BADA sparrarna (bojning, tvarkraft,
    axialkraft, interaktion enligt EC5 6.2.3/6.3.2), i varje lastfall med
    det lastfallets k_mod
  - nockforbandet: momentstyvt enligt 5.3.4.1 eller ledat enligt 5.3.7
  - upplagstrycket vid takfoten enligt ETA 12/0018 ekv. 3-5
  - nedbojning i bruksgranstillstand med skjuvdeformation och k_def
    uppdelad i boj- och skjuvdel (ETA tab. 18)

Tva metodval vart att kanna till:

k_mod per kombination. EN 1995-1-1 3.1.3(2): k_mod svarar mot den KORTAST
varande lasten i kombinationen. En kombination med vind far darfor
momentan-k_mod (1,10) -- vilket kan gora den MINDRE farlig an samma
kombination utan vind, dar k_mod ar 0,80. Darfor provas varje kombination
bade med och utan vindlasten; fallet utan vind ar ofta det som styr.

Rotationsfjadern. Ett spikat skivforband ar inte oandligt styvt: nocken
modelleras med K_r = sum(K * n_snitt * I_p) over spikgrupperna
(elasticitetsteori, samma I_p som kapacitetsformeln), med K_u = 2/3*K_ser i
brottgranstillstand (EC5 2.2.2(2)) och K_ser i bruksgranstillstand
(tab. 7.1). En helt styv nock OVERSKATTAR nockmomentet -- konservativt for
forbandet -- men UNDERSKATTAR faltmoment och nedbojning, vilket ar
okonservativt. Fjadern kan stangas av i projektfilen.
"""

from dataclasses import dataclass, field
from math import cos, radians, sqrt

import numpy as np

import balk as B
import forbindare_ec5 as EC5
import kombinationer as K
import laster as L
import material
import upplag as U
from forband import (Forbindargrupp, Skiva, kontrollera, ledad_nock,
                     rader_langs_balken,
                     rutnat, sym)
from ram import sadeltak

# ETA tab. 11/12 ar deklarerade for C30-flansar -- kvalitetskolumnen sager
# "C30" pa varje rad. Allt som harleds ur tabellernas EI hor darfor ihop
# med den kvaliteten, oavsett vad anvandaren valt i [forband].
TABELLKVALITET = "C30plus"

# psi-faktorerna kommer ur BFS 2024:6 tab. 3:6 via biblioteket. Snons
# varden ar SNOZONBEROENDE i tre band (1/1,5 - 2/2,5 - 3 och uppat), sa
# de gar inte att ha som konstanter: de slas upp ur S_0.
PSI0_VIND = material.psi("vind")["psi0"]
PSI1_VIND = material.psi("vind")["psi1"]
PSI2_VIND = material.psi("vind")["psi2"]   # 0: vind som foljelast faller
                                           # bort ur frekventa komb.


def psi0_sno(S_0):
    """Kombinationsvarde, BFS 2024:6 tab. 3:6."""
    return material.psi_sno(S_0)["psi0"]


def psi1_sno(S_0):
    """Frekvent varde, BFS 2024:6 tab. 3:6."""
    return material.psi_sno(S_0)["psi1"]


def psi2_sno(S_0):
    """
    Kvasipermanent varde, BFS 2024:6 tab. 3:6. Det var forr en konstant
    0,2 -- fel for snozon 1 och 1,5, dar tabellen sager 0,1. Vardet gar
    in bade i u_fin (krypdelen) och i kvasipermanenta kombinationen.
    """
    return material.psi_sno(S_0)["psi2"]


# ---------------------------------------------------------------------------
# Resultatstrukturer
# ---------------------------------------------------------------------------

@dataclass
class Snittkraft:
    kombination: str
    snofall: str
    vindfall: str           # "-" nar kombinationen provas utan vind
    M: float                # kNm
    N: float                # kN
    V: float                # kN
    varaktighet: str = "medel"


@dataclass
class Balksnitt:
    """
    Ett snitt langs en sparre med SAMVERKANDE snittkrafter -- M, N och V i
    samma punkt, sa att interaktionskontrollen blir riktig.

    s   avstand fran takfoten langs sparren [m]
    N   POSITIV = DRAG (som i ram.internal())
    M   POSITIV = drag i underkant, dvs overflansen tryckt
    """
    kombination: str
    snofall: str
    vindfall: str
    sparre: str
    s: float
    M: float
    N: float
    V: float
    utnyttjande: float
    varaktighet: str


@dataclass
class Grupp:
    namn: str
    forbindare: object
    kapacitet: EC5.Kapacitet
    F_v_Rd: float               # kN per snitt, i dimensionerande fallet
    n_snitt: int
    antal: int
    grupp: Forbindargrupp
    intrangning: EC5.Intrangning = None


@dataclass
class Nedbojning:
    L_sparre: float             # fri spannvidd = sparrelangd [m]
    krav_namn: str
    kontroller: list            # B.Kontroll: u mot grans, i mm
    fall_inst: str
    fall_fin: str
    skjuvandel_fin: float       # skjuvdelens andel av u_fin
    fall_freq: str = ""
    overhojd_mm: float = 0.0    # EFFEKTIV overhojning, efter kapning
    overhojd_varning: str = ""  # satt nar angiven overhojning kapades
    anmarkningar: list = field(default_factory=list)

    @property
    def ok(self):
        return all(k.ok for k in self.kontroller)


@dataclass
class Resultat:
    g_k: float
    q_g: float
    snofall: list
    vindfall: list                      # laster.Vindfall, [] om vind saknas
    snittkrafter: list                  # Snittkraft i nocken, alla fall
    dimensionerande: Snittkraft         # varsta nocksnittet (forbandet)
    balk: material.Balk
    balksnitt: Balksnitt
    balkkontroller: list
    hogmoment: Balksnitt
    L_ef: float
    K_r: dict                           # {} nar fjadern ar avstangd
    nocktyp: str                        # "momentstyv" | "ledad"
    skivmaterial: material.Skivmaterial
    flanskvalitet: str
    metod: str
    skivor_handbok: list
    skivor_i_planet: list
    grupper: list
    kontroll: object                    # forband.Resultat (momentstyv nock)
    kontroll_handbok: object
    ledad: object                       # forband.LedadNock | None
    upplag_kontroller: list             # B.Kontroll
    H_takfot: float                     # kN, horisontalkraft i vaggkron
    nedbojning: Nedbojning
    varningar: list = field(default_factory=list)
    antaganden: list = field(default_factory=list)

    @property
    def bada_metoderna_gar(self):
        return self.skivor_i_planet is not None

    @property
    def balken_haller(self):
        return all(k.ok for k in self.balkkontroller)

    @property
    def varsta_balkkontroll(self):
        return B.varsta(self.balkkontroller)

    @property
    def forband_utnyttjande(self):
        """Nockforbandets utnyttjande, oavsett nocktyp."""
        if self.nocktyp == "ledad":
            return self.ledad.utnyttjande
        return self.kontroll.utnyttjande_totalt

    @property
    def upplag_utnyttjande(self):
        return max((k.utnyttjande for k in self.upplag_kontroller),
                   default=0.0)

    @property
    def upplaget_haller(self):
        return all(k.ok for k in self.upplag_kontroller)

    @property
    def varsta_utnyttjande(self):
        """Takstolens varsta utnyttjande: balk, nockforband, nedbojning.

        Upplaget ingar INTE utan redovisas separat (upplag_utnyttjande):
        det styrs av upplagslangd och forstarkning -- en vaggdetalj --
        inte av balkvalet, och ska darfor varken falla takstolen eller
        styra sokningen i dimensionera.foresla. Anvandarbeslut 2026-08-18.
        """
        u = [self.varsta_balkkontroll.utnyttjande, self.forband_utnyttjande]
        u += [k.utnyttjande for k in self.nedbojning.kontroller]
        return max(u)

    @property
    def haller(self):
        """Balk + forband + nedbojning. Upplaget redovisas separat."""
        return (self.balken_haller and self.forband_utnyttjande <= 1.0
                and self.nedbojning.ok)


# ---------------------------------------------------------------------------
# Spikgrupper (geometri och karakteristisk kapacitet ar fallOBEROENDE;
# bara k_mod skiljer mellan lastfallen)
# ---------------------------------------------------------------------------

def ryms_i_skivhojd(hojd, s):
    """
    Antal symmetriska spikkolumner (+/-(s/2 + i*s)) som ryms inom en
    skiva med hojden `hojd` [mm]: storsta k med s/2 + (k-1)*s <= hojd/2.
    """
    return int(hojd / (2.0 * s) + 0.5)


def _skivpassning(namn, coords, hojd):
    """Varnar om nagon forbindare hamnar utanfor skivans hojd (x-led)."""
    if not coords:
        return []
    ytterst = max(abs(x) for x, _ in coords)
    if ytterst > hojd / 2.0 + 1e-9:
        return [f"{namn}: yttersta förbindaren ligger {ytterst:.0f} mm "
                f"från tyngdpunkten men skivan är bara {hojd:.0f} mm hög "
                f"(+/-{hojd / 2:.0f} mm). Förbindare utanför skivan får "
                f"inte räknas i I_p, n eller N_Rd."]
    return []


def flanskolumner(ff, h_flans, kolumner, rho_k=380.0):
    """
    x-forskjutningar for spikkolumnerna inom flansens hojd samt varning
    om de inte ryms enligt EN 1995-1-1 tab. 8.2.

    Kolumnerna laggs symmetriskt kring flansens centrumlinje med
    inbordes avstand a2 = 5d. Kantavstandet kontrolleras mot a4,t
    (belastad kant, alpha = 90 grader): i nockforbandet ar flansspikens
    kraft i huvudsak vinkelrat fibrerna (M*r/Ip ar vinkelrat radien och
    flansspikarna sitter vid stora |x|), sa bada kanterna raknas som
    belastade. Kravet blir 2*a4t + (n-1)*a2 = (14 + 5(n-1))*d <= 47 mm,
    dvs en andra kolumn ryms forst nar d <= 2,4 mm.

    Zigzag-regeln (handboken s. 284, minst 1d forskjutning sa att
    spikarna inte hamnar i samma fiber) uppfylls mellan kolumner av att
    varannan kolumn forskjuts en halv delning i langsled; for en ensam
    kolumn ar den ett utforandekrav som redovisas bland antagandena.
    """
    krav = EC5.minsta_avstand(ff, alpha=90.0, rho_k=rho_k)
    varningar = []
    behov = 2 * krav["a4t"] + (kolumner - 1) * krav["a2"]
    if behov > h_flans + 1e-9:
        ryms = max(1, 1 + int((h_flans - 2 * krav["a4t"]) // krav["a2"]))
        varningar.append(
            f"{kolumner} spikkolumner i flänsen kräver {behov:.1f} mm "
            f"flänshöjd (2*a4t + (n-1)*a2, tab. 8.2 med kraft mot "
            f"belastad kant) men flänsen är {h_flans:.0f} mm hög: "
            f"högst {ryms} kolumn(er) ryms med d = {ff.d} mm.")
    off = [(j - (kolumner - 1) / 2) * krav["a2"] for j in range(kolumner)]
    return off, varningar


def spikgrupper(balk, fb, flanskvalitet, taklutning_grader=0.0):
    """
    Bygger nockforbandets tva spikgrupper med EC5-kapacitet per snitt
    (karakteristisk) och geometri. Dimensionerande varden fas genom att
    skala med lastfallets k_mod -- se skala_grupper().
    """
    skiva_mtrl = material.skiva(fb["skivmaterial"], fb["skiva_t"])
    t_skiva = fb["skiva_t"]
    rho_flans = material.flanskvaliteter()[flanskvalitet]["rho_k"]

    def f_h_skiva(d):
        if skiva_mtrl.nyckel == "plywood_handbok":
            return EC5.f_h_plywood(skiva_mtrl.rho_k, d)
        return EC5.f_h_osb_spanskiva(d, t_skiva)

    s = fb["cc_forbindare"]
    varningar = []

    # Flansgruppen: enkelsnitt skiva -> flans
    ff = material.forbindare(fb["forbindare_flans"])
    kap_f = EC5.enkelsnitt(ff, f_h_skiva(ff.d), t_skiva,
                           EC5.f_h_tra(rho_flans, ff.d, ff.forborrning),
                           ff.langd - t_skiva)
    from math import radians as _rad
    alfa = _rad(taklutning_grader)
    kf = int(fb.get("kolumner_flans", 1))
    off_kol, v_kol = flanskolumner(ff, balk.h_flans, kf, rho_flans)
    varningar.extend(v_kol)
    # Kantavstand mot den kapade anden: 15d = a3t:s ovre grans
    # ((10 + 5*cos alfa)*d, tab. 8.2, BELASTAD ande). I en momentbelastad
    # spikgrupp pekar nagon fognara spiks kraft alltid mot anden --
    # spegelsymmetrin (x, +/-y) garanterar det -- sa a3c = 10d racker
    # inte som generellt krav. Granskning 2026-08-19 belade 10d-brott i
    # varje momentstyv korning.
    kant_f = 15.0 * ff.d
    # SIDOFORSKJUTNING (2026-08-19, anvandarbeslut): spik fran motstaende
    # sidor far inte sitta mitt for varandra -- flansspiken overlappar
    # 2*(langd - t) - b_flans i flansen och livspiken delar samma
    # genomgaende linje. Sida -Y forskjuts darfor `sidoforskjutning`*s
    # FRAN fogen (mot fogen skulle bryta 15d-kravet), i sjalva
    # koordinaterna: I_p, K_r, skivlangder, ritning och CSV foljer da
    # automatiskt. 0 aterger den spegelplacerade bilden (handbokens).
    fs = float(fb.get("sidoforskjutning", 0.0)) * s
    rbas = float(fb.get("rutnat_bas", 0.5))
    # Rasterankare "flansvinkel": en tvarlinje gar exakt genom vinkeln
    # mellan undre flansarna, (h/2)*tan(alfa) fran fogen langs balken.
    from math import tan as _tan
    ank = ((balk.h / 2) * _tan(alfa)
           if fb.get("rutnat_ankare", "") == "flansvinkel" else None)
    coords_flans, coords_flans_b = [], []
    for j, off in enumerate(off_kol):
        for xc in (-balk.c_flans / 2, balk.c_flans / 2):
            # Zigzag: varannan kolumn forskjuts en halv delning (s. 284)
            ys = rader_langs_balken(
                xc + off, fb["rader_flans"], s, alfa, kant_f,
                forskjut=(s / 2 if j % 2 else 0), bas_andel=rbas,
                ankare=ank)
            # Sida B = sida A + fs, som REN addition: att i stallet ge
            # rader_langs_balken forskjut=fs vore fel, eftersom dess
            # max()-klampning mot kantkravet nollar forskjutningen i
            # fognara kolonner -- och da star spikarna mitt for varandra
            # igen, precis dar de ar som tatast.
            coords_flans += [(xc + off, tecken * y)
                             for y in ys for tecken in (1, -1)]
            coords_flans_b += [(xc + off, tecken * (y + fs))
                               for y in ys for tecken in (1, -1)]
    g_flans = Forbindargrupp(
        "Forbindare -> flans", kap_f.F_v_Rk_kN, 1,
        coords=coords_flans + coords_flans_b)
    g_flans.sidor = (coords_flans, coords_flans_b)
    flans = Grupp("Forbindare -> flans", ff, kap_f, kap_f.F_v_Rk_kN, 1,
                  g_flans.n, g_flans)

    # Livet ar indraget (b_flans - t_liv)/2 fran flansarnas sidor.
    # Livforstarkningen ska fylla den indragningen -- forst da ligger
    # balksidan plan sa att den utanpaliggande skivan bar mot BADA
    # flansarna. Ar skivan tunnare spanner den over en glipa och far en
    # bojning som ingen av kontrollerna raknar med.
    indrag = (balk.b_flans - balk.t_liv) / 2.0
    if t_skiva < indrag - 2.0:
        varningar.append(
            f"Livförstärkningen är {t_skiva:.0f} mm men livet är indraget "
            f"{indrag:.1f} mm från flänssidan på {balk.namn}. Den "
            f"utanpåliggande skivan spänner då över en glipa på "
            f"{indrag - t_skiva:.1f} mm i stället för att ligga an mot "
            f"livförstärkningen. Använd {indrag:.0f} mm livförstärkning "
            f"(eller mellanlägg) -- annars böjs den yttre skivan, och det "
            f"räknar ingen av kontrollerna med.")
    elif t_skiva > indrag + 2.0:
        varningar.append(
            f"Livförstärkningen är {t_skiva:.0f} mm men indragningen bara "
            f"{indrag:.1f} mm på {balk.namn}: den bygger utanför "
            f"flänssidan, så den utanpåliggande skivan får inte kontakt "
            f"med flänsarna.")

    krav_t = EC5.minsta_tjocklek_mot_sprickning(ff, rho_flans)
    if balk.b_flans < krav_t:
        varningar.append(
            f"Flänsen är {balk.b_flans:.0f} mm bred men 8.3.1.2 kräver "
            f"{krav_t:.1f} mm för att spika {ff.namn} utan förborrning.")

    # Livgruppen: dubbelsnitt skiva -> liv -> skiva om intrangningen racker
    fl = material.forbindare(fb["forbindare_liv"])
    liv_mtrl = material.skiva(_livskiva(balk.liv), balk.t_liv)
    f_h_liv = (EC5.f_h_plywood(liv_mtrl.rho_k, fl.d)
               if liv_mtrl.nyckel == "plywood_handbok"
               else EC5.f_h_osb_spanskiva(fl.d, balk.t_liv))

    intr = EC5.kontrollera_intrangning(fl, [t_skiva, balk.t_liv, t_skiva])
    if intr.uppfyllt:
        kap_l = EC5.dubbelsnitt(fl, f_h_skiva(fl.d), t_skiva, f_h_liv,
                                balk.t_liv)
        n_snitt = 2
    else:
        kap_l = EC5.enkelsnitt(fl, f_h_skiva(fl.d), t_skiva, f_h_liv,
                               balk.t_liv)
        n_snitt = 1
        varningar.extend(intr.fel)
    varningar.extend(intr.anmarkningar)

    # Spikmonster for livgruppen:
    #   "rutnat"  fullt rutnat kolumner x rader (dagens enklaval)
    #   "kant"    handbokens RAM (fig. 5.30, s. 289): rader langs skivans
    #             over- och underkant + fulla kolumner i de yttersta
    #             `rader_andblock` raderna vid skivans andar, tomt i
    #             mitten. Behall spik om kolumnen ar den yttersta ELLER
    #             raden hor till andblocket. Regeln reproducerar exakt
    #             handbokens n = 64 och I_p = 1,26e6 mm2 (12/12/12/28 per
    #             x-niva, 4/16 per y-niva) -- last av test.
    monster = fb.get("spikmonster", "rutnat")
    if monster not in ("rutnat", "kant"):
        raise ValueError(f"spikmonster = {monster!r} -- välj 'rutnat' "
                         f"eller 'kant'")
    andblock = int(fb.get("rader_andblock", 3))
    kant_l = 15.0 * fl.d
    x_kolumner = sym(s / 2, s, fb["kolumner_liv"])
    x_max = max(abs(x) for x in x_kolumner)
    coords_liv, coords_liv_b = [], []
    for x in x_kolumner:
        ys = rader_langs_balken(x, fb["rader_liv"], s, alfa, kant_l,
                                bas_andel=rbas, ankare=ank)
        for i, y in enumerate(ys):
            if (monster == "kant" and abs(x) < x_max - 1e-9
                    and i < fb["rader_liv"] - andblock):
                continue                       # ramens tomma mitt
            # sida B = sida A + fs (ren addition, se flanskommentaren)
            coords_liv += [(x, y), (x, -y)]
            coords_liv_b += [(x, y + fs), (x, -(y + fs))]
    g_liv = Forbindargrupp(
        "Forbindare -> liv", kap_l.F_v_Rk_kN, n_snitt,
        coords=coords_liv + coords_liv_b)
    g_liv.sidor = (coords_liv, coords_liv_b)
    liv = Grupp("Forbindare -> liv", fl, kap_l, kap_l.F_v_Rk_kN, n_snitt,
                g_liv.n, g_liv, intr)

    varningar += _skivpassning("Livförstärkningen", g_liv.coords,
                               fb["skiva_hojd_liv"])
    varningar += _skivpassning("Utanpåliggande skivan", g_flans.coords,
                               fb["skiva_hojd_ytter"])

    for gr in (flans, liv):
        krav = EC5.minsta_avstand(gr.forbindare, rho_k=rho_flans)
        if s < krav["a1"]:
            varningar.append(
                f"{gr.namn}: c/c {s:.1f} mm < a1 = {krav['a1']:.1f} mm "
                f"(tab. 8.2).")
    return [flans, liv], skiva_mtrl, varningar


def _livskiva(liv):
    return {"osb": "osb3", "spanskiva": "p5"}[liv]


def k_mod_forband(skiva_nyckel, klimatklass, varaktighet):
    """
    k_mod for forbandet mellan skiva och tra/liv, EN 1995-1-1 2.3.2.1(2):
    for delar med olika k_mod galler k_mod = sqrt(k_mod_1 * k_mod_2).
    Travardena i ETA tab. 17:s bojningsrad AR EC5:s rad for massivt tra,
    sa den anvands som travardet. For plywood ger det samma tal som
    handbokens (bada 0,8 vid medellang last).
    """
    k1 = material.k_mod_skiva(skiva_nyckel, klimatklass, varaktighet)
    k2 = material.k_mod_bojning(klimatklass, varaktighet)
    return sqrt(k1 * k2)


def skala_grupper(grupper, k_mod, gamma_M):
    """Forbindargrupper med dimensionerande kraft for ett visst k_mod."""
    ut = []
    for gr in grupper:
        F_Rd = gr.kapacitet.F_v_Rd_kN(k_mod, gamma_M)
        g = Forbindargrupp(gr.namn, F_Rd, gr.n_snitt, n=gr.grupp.n,
                           Ip=gr.grupp.Ip, r=gr.grupp.r)
        g.coords = gr.grupp.coords
        if hasattr(gr.grupp, "sidor"):
            g.sidor = gr.grupp.sidor
        ut.append((gr, g, F_Rd))
    return ut


def _skivsatser(fb, skiva_mtrl, k_mod, gamma_skiva):
    """Skivornas kapacitet, med f_m (handbok) och f_t,0 (i planet)."""
    def satts(hallfasthet):
        return [
            Skiva("Livforstarkning", fb["skiva_t"], fb["skiva_hojd_liv"], 2,
                  hallfasthet, k_mod, gamma_skiva),
            Skiva("Utanpaliggande skiva", fb["skiva_t"],
                  fb["skiva_hojd_ytter"], 2, hallfasthet, k_mod, gamma_skiva),
        ]
    handbok = satts(skiva_mtrl.bojhallfasthet())
    i_planet = (satts(skiva_mtrl.draghallfasthet())
                if skiva_mtrl.har_draghallfasthet else None)
    return handbok, i_planet


# ---------------------------------------------------------------------------
# Rotationsfjader
# ---------------------------------------------------------------------------

def halvgruppernas_Ip(coords):
    """
    (I_vanster, I_hoger) -- varje halvgrupps polara troghetsmoment om SIN
    EGEN tyngdpunkt [mm2]. Halvorna delas vid fogen, y = 0, dar y ar
    langs balken.
    """
    ut = []
    for tecken in (-1, 1):
        halv = [(x, y) for x, y in coords if tecken * y > 0]
        if not halv:
            ut.append(0.0)
            continue
        xm = sum(x for x, _ in halv) / len(halv)
        ym = sum(y for _, y in halv) / len(halv)
        ut.append(sum((x - xm) ** 2 + (y - ym) ** 2 for x, y in halv))
    return tuple(ut)


def rotationsstyvhet(grupper, flanskvalitet, taklutning_grader=0.0):
    """
    Nockforbandets rotationsstyvhet [kNm/rad].

    Nocken ar en SKARV: skivorna ar spikade i vanster sparre av
    forbindarna pa ena sidan fogen och i hoger sparre av de pa den
    andra, sa halvforbanden sitter i SERIE och styvheten raknas pa
    halvgruppernas troghetsmoment om SIN EGEN tyngdpunkt -- skivan ar
    fri att translatera, sa Steiners term hor inte hit. Se
    EC5.K_rot_skarv for harledningen och varningen.

    K_ser per forbindare och snitt ur EC5 tab. 7.1 med flansens
    MEDELdensitet (EN 338). Att anvanda travardet aven for snittet mot
    skivan ar ett antagande -- skivornas medeldensitet ar inte deklarerad
    i EN 12369-1 -- och redovisas som ett sadant.
    """
    from math import radians as _rad
    rho_m = material.flanskvaliteter()[flanskvalitet]["rho_mean"]
    alfa = _rad(taklutning_grader)
    data = [(gr.forbindare, gr.n_snitt, gr.grupp.coords) for gr in grupper]
    halvor = [(gr.forbindare, gr.n_snitt, *halvgruppernas_Ip(gr.grupp.coords))
              for gr in grupper]
    hel = [(gr.forbindare, gr.n_snitt, gr.grupp.Ip) for gr in grupper]
    return dict(
        K_ser=EC5.K_rot_skarv_vriden(data, rho_m, alfa, brottgrans=False),
        K_u=EC5.K_rot_skarv_vriden(data, rho_m, alfa, brottgrans=True),
        K_platt=EC5.K_rot_skarv(halvor, rho_m, brottgrans=False),
        K_en_stel_del=EC5.K_rot(hel, rho_m, brottgrans=False),
        taklutning=taklutning_grader, rho_m=rho_m)


# ---------------------------------------------------------------------------
# Sidostod
# ---------------------------------------------------------------------------

def sidostodskontroll(balk, geometri, hogmoment):
    """
    ETA annex 3 tab. 19: den deklarerade momentkapaciteten galler bara nar
    TRYCKFLANSEN ar sidostodd med hogst sidostod_max. Vid negativt moment
    ar det underflansen som ar tryckt, och taklakten sitter pa oversidan.
    Kontrollen varnar och rakningen fortsatter sa att konsekvensen syns.
    """
    varningar = []
    cc_lakt = geometri.get("cc_lakt", 0.0) * 1000.0
    cc_under = geometri.get("sidostod_underflans", 0.0)

    if cc_lakt <= 0:
        varningar.append(
            "cc_lakt saknas i projektfilen. Utan den går sidostödet av "
            "överflänsen inte att prova mot ETA tab. 19.")
    elif not B.sidostod_racker(balk, cc_lakt):
        varningar.append(
            f"Överflänsen: sidostöd var {cc_lakt:.0f} mm men ETA tab. 19 "
            f"kräver högst {balk.sidostod_max:.0f} mm för serie "
            f"{balk.serie}. Den deklarerade M_k gäller inte.")

    if hogmoment is not None and hogmoment.M < -1e-9:
        var = (f"{hogmoment.s:.2f} m från takfoten på {hogmoment.sparre} "
               f"sparre")
        if cc_under <= 0:
            varningar.append(
                f"Största negativa momentet är {hogmoment.M:.2f} kNm, {var}. "
                f"Då är UNDERFLÄNSEN tryckt där, och något sidostöd av den "
                f"är inte angivet. ETA tab. 19 kräver högst "
                f"{balk.sidostod_max:.0f} mm för serie {balk.serie}. "
                f"Takläkten sitter på översidan och hjälper inte här.")
        elif not B.sidostod_racker(balk, cc_under):
            varningar.append(
                f"Underflänsen är tryckt {var} (M = {hogmoment.M:.2f} kNm) "
                f"och dess sidostöd var {cc_under:.0f} mm, men ETA tab. 19 "
                f"kräver högst {balk.sidostod_max:.0f} mm.")
    return varningar


def _sparrelangd(spannvidd, taklutning_grader):
    return (spannvidd / 2) / cos(radians(taklutning_grader))


# ---------------------------------------------------------------------------
# Nedbojning
# ---------------------------------------------------------------------------

def _avvikelse_fran_korda(fr, noder):
    """
    Nodernas forskjutning vinkelratt kordan mellan sparrens andpunkter,
    relativt den rata linjen mellan andarnas forskjutna lagen [m].
    Det ar "nedbojningen" for en snedstalld sparre.
    """
    xa, ya = fr.nodes[noder[0]]
    xb, yb = fr.nodes[noder[-1]]
    dx, dy = xb - xa, yb - ya
    Ln = sqrt(dx * dx + dy * dy)
    nx, ny = -dy / Ln, dx / Ln
    dev = np.array([fr.node_disp(n)[0] * nx + fr.node_disp(n)[1] * ny
                    for n in noder])
    # t ur nodens LAGE langs kordan, inte ur dess index: elementen
    # behover inte vara lika langa (takstol_b1 delar sparren vid
    # hanbjalken), och en indexparametrisering ger da fel korda.
    t = np.array([((fr.nodes[n][0] - xa) * dx
                   + (fr.nodes[n][1] - ya) * dy) / (Ln * Ln)
                  for n in noder])
    return dev - ((1 - t) * dev[0] + t * dev[-1])


def _sls_falt(bygg_ram, lastsattare):
    """
    Loser ett SLS-lastfall tva ganger -- med och utan skjuvdeformation --
    och returnerar (boj, skjuv) per sparre som nodfalt. Skjuvdelen ar
    differensen; de tva delarna har olika k_def enligt ETA tab. 18.
    """
    ut = {}
    for med_skjuv in (False, True):
        fr, ix = bygg_ram(med_skjuv)
        lastsattare(fr, ix)
        fr.solve()
        ut[med_skjuv] = {sida: _avvikelse_fran_korda(fr, ix[f"{sida}_noder"])
                         for sida in ("vanster", "hoger")}
    boj = ut[False]
    skjuv = {s: ut[True][s] - ut[False][s] for s in boj}
    return boj, skjuv


def nedbojningsberakning(cfg, balk, q_g, snofall, vindfall, K_r_ser):
    """
    u_inst ur den karakteristiska kombinationen och u_fin enligt
    EN 1995-1-1 2.2.3(5), bada uppdelade i bojdel och skjuvdel med olika
    k_def (ETA tab. 18). Kravnivaerna ur handboken s. 229 via
    input/material/nedbojningskrav.toml.
    """
    g, sysm, p = cfg["geometri"], cfg["system"], cfg["projekt"]
    nb = cfg.get("nedbojning", {})
    kk = p["klimatklass"]
    cc = g["cc"]

    kdef_b = material.k_def_bojning(kk)
    kdef_s = material.k_def_skjuvning(balk.liv, kk)
    s_k = lastforutsattningar(cfg)[0]      # S_0, mark
    psi1_s = psi1_sno(s_k)
    psi0_s = psi0_sno(s_k)
    psi2_s = psi2_sno(s_k)

    def bygg(med_skjuv):
        return sadeltak(g["spannvidd"], g["taklutning"],
                        EA=balk.EA(cfg["forband"].get("flanskvalitet",
                                                      "C30plus")),
                        EI=balk.EI, GA=balk.GA if med_skjuv else None,
                        nock_styv=sysm["nock_styv"],
                        dragband=sysm["dragband"], upplag=sysm["upplag"],
                        n_elem=12, K_r=K_r_ser)

    def last_g(fr, ix):
        for e in ix["vanster"] + ix["hoger"]:
            fr.set_udl_projected(e, -q_g)

    falt = {"G": _sls_falt(bygg, last_g)}

    for f in snofall:
        def last_s(fr, ix, f=f):
            for e in ix["vanster"]:
                fr.set_udl_projected(e, -L.linjelast(f.s_vanster, cc))
            for e in ix["hoger"]:
                fr.set_udl_projected(e, -L.linjelast(f.s_hoger, cc))
        falt[f.namn] = _sls_falt(bygg, last_s)

    for v in vindfall:
        def last_v(fr, ix, v=v):
            for e in ix["vanster"]:
                fr.set_udl_local(e, -v.w_vanster * cc)
            for e in ix["hoger"]:
                fr.set_udl_local(e, -v.w_hoger * cc)
        falt[v.namn] = _sls_falt(bygg, last_v)

    def maxdev(*termer):
        """max |sum av (faktor, bojfalt, skjuvfaktor...)| over alla noder."""
        varsta = 0.0
        for sida in ("vanster", "hoger"):
            tot = sum(fb * b[sida] + fs * s[sida] for fb, fs, (b, s) in termer)
            varsta = max(varsta, float(np.max(np.abs(tot))))
        return varsta * 1000.0          # m -> mm

    G = falt["G"]
    u_inst = u_fin = u_freq = -1.0
    fall_inst = fall_fin = fall_freq = ""
    skjuvandel = 0.0
    vindnycklar = [None] + [v.namn for v in vindfall]
    for f in snofall:
        S = falt[f.namn]
        for vn in vindnycklar:
            Vf = falt[vn] if vn else None
            namn = f.namn + (f" + {vn}" if vn else "")

            # EN 1990 ekv. 6.14a (karakteristisk kombination): VARJE
            # variabel last ska i tur och ordning provas som ledande.
            # Med sno ledande gar vinden in med psi_0 och tvartom -- pa
            # en blasig ort med lag snozon styr vind-ledande fallet.
            kandidater = [(namn + (", snö ledande" if Vf else ""),
                           [(1.0, 1.0, G), (1.0, 1.0, S)]
                           + ([(PSI0_VIND, PSI0_VIND, Vf)] if Vf else []))]
            if Vf:
                kandidater.append(
                    (namn + ", vind ledande",
                     [(1.0, 1.0, G), (1.0, 1.0, Vf),
                      (psi0_s, psi0_s, S)]))
            for kombinamn, termer in kandidater:
                u = maxdev(*termer)
                if u > u_inst:
                    u_inst, fall_inst = u, kombinamn

            # Frekvent kombination, Limtrahandboken del 2 ekv. 6.8:
            # G + psi_1,1*Q_1 + sum(psi_2,i*Q_i). Momentan nedbojning,
            # ingen krypdel -- tab. 6.1:s fotnot ger den har vagen
            # eftersom SS-EN 1995 saknar anvisning for frekvent komb.
            # Bada ledande valen provas; med sno ledande faller vinden
            # bort eftersom PSI2_VIND = 0.
            if vn is None:
                u = maxdev((1.0, 1.0, G), (psi1_s, psi1_s, S))
                if u > u_freq:
                    u_freq, fall_freq = u, f"{f.namn}, snö ledande"
            else:
                u = maxdev((1.0, 1.0, G), (psi2_s, psi2_s, S),
                           (PSI1_VIND, PSI1_VIND, Vf))
                if u > u_freq:
                    u_freq, fall_freq = u, f"{namn}, vind ledande"

            # EN 1995-1-1 2.2.3(5): u_fin,G = u_G(1+k_def),
            # u_fin,Q1 = u_Q1(1+psi_2,1*k_def) och
            # u_fin,Qi = u_Qi(psi_0,i + psi_2,i*k_def). Aven har provas
            # bada ledande valen; psi_2 for vind ar 0.
            kandidater = [(namn + (", snö ledande" if Vf else ""),
                           [(1 + kdef_b, 1 + kdef_s, G),
                            (1 + psi2_s * kdef_b,
                             1 + psi2_s * kdef_s, S)]
                           + ([(PSI0_VIND + PSI2_VIND * kdef_b,
                                PSI0_VIND + PSI2_VIND * kdef_s, Vf)]
                              if Vf else []))]
            if Vf:
                kandidater.append(
                    (namn + ", vind ledande",
                     [(1 + kdef_b, 1 + kdef_s, G),
                      (1 + PSI2_VIND * kdef_b, 1 + PSI2_VIND * kdef_s, Vf),
                      (psi0_s + psi2_s * kdef_b,
                       psi0_s + psi2_s * kdef_s, S)]))
            for kombinamn, termer in kandidater:
                u = maxdev(*termer)
                if u > u_fin:
                    u_fin, fall_fin = u, kombinamn
                    skjuv = maxdev(*[(0.0, fs, falt_)
                                     for _, fs, falt_ in termer])
                    skjuvandel = skjuv / u if u > 0 else 0.0

    L_sp = _sparrelangd(g["spannvidd"], g["taklutning"])
    krav = material.nedbojningskrav(nb.get("byggnadstyp",
                                           "allmant_utan_tak"))
    overhojd = bool(nb.get("overhojd", False))
    faktor = (material.NEDBOJNING_DATA["metadata"]["overhojd_faktor"]
              if overhojd else 1.0)

    # Overhojningen ar en GEOMETRISK forskjutning: den syns inte i ramens
    # nedbojning utan dras av efterat. Handboken s. 229 och
    # Limtrahandboken tab. 6.1 tabellerar "ej overhojda" element och
    # sager "tabellvardet/1,5" for overhojda -- alltsa en STRAMARE grans,
    # vilket bara ar meningsfullt mot NETTOnedbojningen u - u_c (samma
    # storhet som EC5 kallar w_net,fin). Utan angiven overhojning i mm
    # jamfors annars en brutto-nedbojning mot ett netto-krav. Se
    # docs/ERRATA.md punkt 6.
    u_c = float(nb.get("overhojd_mm", 0.0)) if overhojd else 0.0
    if overhojd and u_c <= 0.0:
        raise ValueError(
            "nedbojning.overhojd = true kräver overhojd_mm > 0: kravet "
            "skärps med 1,5 och gäller då NETTOnedböjningen u - u_c "
            "(handboken s. 229, Limträhandboken tab. 6.1). Ange "
            "överhöjningen i mm eller sätt overhojd = false.")

    # Overhojningen kapas vid EGENTYNGDENS SLUTLIGA nedbojning (med
    # krypning). Overhojningen finns for att kompensera just den --
    # Limtrahandboken 6.2.4 s. 87: "bor nedbojningsgransen tillampas
    # endast pa den del som fororsakas av nyttolasten". Overhojer man
    # mer star balken med en uppatbuktning, och avdraget skulle bli ett
    # sifferknep som kan fa vilken balk som helst att ga igenom.
    u_c_max = maxdev((1 + kdef_b, 1 + kdef_s, G))
    overhojd_varning = ""
    if u_c > u_c_max + 1e-9:
        overhojd_varning = (
            f"Angiven överhöjning {u_c:.0f} mm är större än egentyngdens "
            f"slutliga nedböjning {u_c_max:.1f} mm och kapas dit. Mer "
            f"överhöjning än så ger en uppåtbuktning och får inte "
            f"tillgodoräknas (Limträhandboken 6.2.4 s. 87).")
        u_c = u_c_max

    kontroller, anm = [], []
    if u_c > 0:
        anm.append(f"Överhöjning {u_c:.1f} mm dras från nedböjningen och "
                   f"kraven skärps med faktor 1,5: kontrollen gäller då "
                   f"NETTOnedböjningen u - u_c (handboken s. 229 "
                   f"\"tabular value /1.5\", Limträhandboken tab. 6.1). "
                   f"Kapat vid egentyngdens slutliga nedböjning "
                   f"{u_c_max:.1f} mm. Se docs/ERRATA.md punkt 6.")
    if overhojd_varning:
        anm.append(overhojd_varning)
    referensbas = {"u_inst": "handboken s. 229",
                   "u_freq": "Limträhandbok del 2 ekv. 6.8 + tab. 6.1",
                   "u_fin": "handboken s. 229"}
    for nyckel, u, fall in (("u_inst", u_inst, fall_inst),
                            ("u_freq", u_freq, fall_freq),
                            ("u_fin", u_fin, fall_fin)):
        u = max(u - u_c, 0.0)
        n = krav[nyckel]
        if n <= 0:
            anm.append(f"{nyckel}: handboken anger inget krav för "
                       f"'{krav['namn']}'.")
            continue
        # Handbokens cell ar t.ex. "L/200 (maximum 30 mm)" -- HELA
        # cellen ar "tabellvardet", sa overhojningsfaktorn maste laggas
        # pa bade L/n-termen och mm-taket. Annars sanks u med u_c medan
        # taket star stilla och overhojning gor kontrollen LATTARE.
        grans = L_sp * 1000.0 / n / faktor
        tak = krav.get(f"{nyckel}_max_mm")
        if tak:
            grans = min(grans, tak / faktor)
        kontroller.append(B.Kontroll(
            namn=f"Nedböjning {nyckel.replace('u_', '')}",
            E_d=u, R_d=grans, enhet="mm", utnyttjande=u / grans,
            referens=f"{referensbas[nyckel]}, L/{n}"
                     + (f", högst {tak} mm" if tak else "")
                     + (f", överhöjd {u_c:.1f} mm: netto mot värde/1,5"
                        if faktor != 1.0 else ""),
            formel=f"{u:.1f} mm mot {grans:.1f} mm ({fall})"))
    anm.append(f"u_freq enligt Limträhandboken del 2 ekv. 6.8 (tab. 6.1:s "
               f"fotnot: SS-EN 1995 saknar anvisning för frekvent "
               f"kombination). Momentan nedböjning utan krypdel; snö och "
               f"vind provas var för sig som ledande. psi_1 snö = "
               f"{psi1_s} (snözon ur S_0 = {s_k:g} kN/m2, BFS 2024:6 "
               f"tab. 3:6), "
               f"psi_1 vind = {PSI1_VIND}, psi_2 vind = "
               f"{PSI2_VIND:.0f}.")

    return Nedbojning(L_sparre=L_sp, krav_namn=krav["namn"],
                      kontroller=kontroller, fall_inst=fall_inst,
                      fall_fin=fall_fin, skjuvandel_fin=skjuvandel,
                      fall_freq=fall_freq, overhojd_mm=u_c,
                      overhojd_varning=overhojd_varning,
                      anmarkningar=anm)


# ---------------------------------------------------------------------------
# Hela kedjan
# ---------------------------------------------------------------------------

def _dimensioneringsval(cfg):
    d = cfg.get("dimensionering", {})
    # E05_kvot = 0 (eller utelamnad) betyder HARLED ur EN 338 enligt
    # ETA avsn. 1.2.4. Ett angivet varde overstyr, men da ager du det.
    #
    # Kvoten far INTE tas ur anvandarens flansval: ETA tab. 11/12 ar
    # deklarerade enbart for C30-flansar ("Beam depth and quality: ...
    # C30"), sa EI i biblioteket ar byggt pa E_f = 13 000. Delar man da
    # med ett LAGRE E_f (C24+: 11 000) blir kvoten storre och ett
    # SVAGARE flansval skulle ge en snallare knackningskontroll. Kvoten
    # hor ihop med tabellens kvalitet, inte med valet.
    kvot = d.get("E05_kvot", 0.0) or material.e05_kvot(TABELLKVALITET)
    return {"gamma_M_balk": d.get("gamma_M_balk", 1.30),
            "beta_c": d.get("beta_c", 0.20),
            "E05_kvot": kvot,
            "E05_harledd": not d.get("E05_kvot", 0.0),
            "knacklangdsfaktor": d.get("knacklangdsfaktor", 1.0)}


def lastforutsattningar(cfg):
    """
    S_0 (snolast pa mark) och q_p (vindens hastighetstryck) med besked om
    VAR de kommer ifran.

    Har projektfilen ett [plats.hamtat] galler det: S_0 rakt av, och q_p
    raknat ur v_b enligt BFS 2024:6 4 kap. 38 §. Annars anvands
    [laster.sno].s_k och [laster.vind].q_p som handpaslagna varden.
    Ett q_p > 0 i projektfilen overstyr alltid raknandet.
    """
    v = cfg.get("laster", {}).get("vind", {})
    sno = cfg.get("laster", {}).get("sno", {})
    h = cfg.get("plats", {}).get("hamtat", {})
    kallor = []

    if sno.get("s_k"):
        # Ett angivet varde overstyr alltid det hamtade -- samma regel som
        # for q_p. 0 (eller utelamnat) betyder "anvand det hamtade".
        S_0 = float(sno["s_k"])
        kallor.append(
            f"S_0 = {S_0} kN/m2 är ÖVERSTYRT i [laster.sno].s_k"
            + (f" (det hämtade värdet {h['S_0']} kN/m2 används inte)."
               if h.get("S_0") else " (PLATSHALLARE -- hämta för platsen)."))
    elif h.get("S_0"):
        S_0 = float(h["S_0"])
        kallor.append(
            f"S_0 = {S_0} kN/m2 hämtat för SWEREF99 TM N "
            f"{cfg['plats'].get('x_koord')} E {cfg['plats'].get('y_koord')} "
            f"ur Boverkets Klimatlast-API {h.get('apiversion', '?')} "
            f"{h.get('hamtat_datum', '?')}. Motsvarar BFS 2024:6 4 kap. "
            f"30 §, figur 4:2. API-värdet är vägledning; vid avvikelse "
            f"gäller den tryckta författningen.")
    else:
        S_0 = 0.0
        kallor.append("Snölast saknas: varken [plats.hamtat].S_0 eller "
                      "[laster.sno].s_k är satt.")

    if v.get("q_p"):
        q_p = float(v["q_p"])
        kallor.append(f"q_p = {q_p} kN/m2 är överstyrt i projektfilen.")
    elif h.get("v_b"):
        terr = str(v.get("terrangtyp", ""))
        z = float(v.get("referenshojd", 0.0))
        c_0 = float(v.get("topografifaktor", 1.0))
        if not terr or z <= 0:
            raise ValueError(
                "q_p ska räknas ur v_b men terrangtyp och referenshojd "
                "saknas i [laster.vind]. Terrängtypen (BFS 2024:6 "
                "tab. 4:4) och höjden z är platsbedömningar som "
                "programmet inte får göra åt dig.")
        q_p = L.q_pk(float(h["v_b"]), terr, z, c_0)
        t = material.terrang(terr)
        kallor.append(
            f"q_p = {q_p:.3f} kN/m2 räknat ur v_b = {h['v_b']} m/s enligt "
            f"BFS 2024:6 4 kap. 38 §, terrängtyp {terr} (z_0 = {t['z0']} m, "
            f"z_min = {t['z_min']} m), z = {z:.1f} m, c_0 = {c_0:.2f}. "
            f"Terrängtyp, höjd och topografifaktor är DINA bedömningar.")
    else:
        q_p = 0.0
        kallor.append("Vindlast ingår inte: varken v_b eller q_p finns.")

    return S_0, q_p, kallor


def _vindfall(cfg):
    v = cfg.get("laster", {}).get("vind", {})
    _, q_p, _ = lastforutsattningar(cfg)
    if not q_p or "c_pe_lov" not in v:
        return []
    return L.vindfall(q_p, v["c_pe_lov"], v["c_pe_la"], v["c_pi"])


def kor(cfg: dict) -> Resultat:
    g, sysm, p = cfg["geometri"], cfg["system"], cfg["projekt"]
    fb, kk = cfg["forband"], p["klimatklass"]
    dim = _dimensioneringsval(cfg)
    balk = material.balk(g["balk"])
    flanskval = fb.get("flanskvalitet", "C30plus")
    cc = g["cc"]

    # -- 1. Laster ---------------------------------------------------------
    g_k = L.egentyngd(cfg["laster"]["egentyngd"], g["taklutning"])
    q_g = L.linjelast(g_k, cc)
    S_0, _, lastkallor = lastforutsattningar(cfg)
    sno = L.snolast(S_0, g["taklutning"],
                    cfg["laster"]["sno"]["C_e"], cfg["laster"]["sno"]["C_t"])
    vind = _vindfall(cfg)

    # -- 2. Kombinationer --------------------------------------------------
    laster = [K.Last("g", "egentyngd", g_k), K.Last("s", "sno", 0.0)]
    if vind:
        laster.append(K.Last("v", "vind", 0.0))
    kombos = K.brottgrans(laster, p["sakerhetsklass"],
                          S_0)

    # -- 3. Forband (fallOBEROENDE delar) ----------------------------------
    grupper, skiva_mtrl, fb_varningar = spikgrupper(
        balk, fb, flanskval, g["taklutning"])
    gamma_skiva = material.gamma_M_skiva(skiva_mtrl.nyckel)
    gamma_forb = material.GAMMA_M_FORBAND

    # Nockforbandets metod. "handbok" foljer 5.3.4.1 (hela spikbilden om
    # fogen), "halvgrupp" den elastiska skarvlosningen. Se ERRATA punkt 7.
    nockmetod = fb.get("nockmetod", "handbok")
    if nockmetod not in ("handbok", "halvgrupp"):
        raise ValueError(
            f"forband.nockmetod = {nockmetod!r} -- välj 'handbok' eller "
            f"'halvgrupp'. Se docs/ERRATA.md punkt 7.")
    skarvmetod = nockmetod == "halvgrupp"

    fjader = sysm.get("rotationsfjader", False) and sysm["nock_styv"]
    K_r = (rotationsstyvhet(grupper, flanskval, g["taklutning"])
           if fjader else {})

    # -- 4. Brottgranssvepet -----------------------------------------------
    kmod_cache = {}

    def kmods(varakt):
        if varakt not in kmod_cache:
            kmod_cache[varakt] = (
                material.k_mod_bojning(kk, varakt),
                material.k_mod_tvarkraft(balk.liv, kk, varakt),
                k_mod_forband(skiva_mtrl.nyckel, kk, varakt),
                # Skivans EGNA hallfasthetskontroller (moment, skjuvning)
                # far skivans eget k_mod. sqrt-mixen (EC5 2.3.2.1(2))
                # galler FORBINDARKAPACITET i forband mellan olika
                # material -- inte skivans hallfasthet. For OSB ar mixen
                # ~7 % hogre an skivans eget varde, at osakra hallet.
                material.k_mod_skiva(skiva_mtrl.nyckel, kk, varakt))
        return kmod_cache[varakt]

    L_sparre = _sparrelangd(g["spannvidd"], g["taklutning"])
    L_ef = dim["knacklangdsfaktor"] * L_sparre
    EA = balk.EA(flanskval)

    snittkrafter = []
    varsta_nock = None          # (utnyttjande forband, Snittkraft, objekt)
    balksnitt = hogmoment = None
    R_max = {"vanster": (0.0, None), "hoger": (0.0, None)}
    H_max = 0.0
    ledad_varsta = None
    ledad_snitt = None          # Snittkraften som gav ledad_varsta

    def bygg_uls():
        return sadeltak(g["spannvidd"], g["taklutning"], EA=EA, EI=balk.EI,
                        GA=balk.GA, nock_styv=sysm["nock_styv"],
                        dragband=sysm["dragband"], upplag=sysm["upplag"],
                        n_elem=12,
                        K_r=K_r.get("K_u") if fjader else None)

    for namn, fakt, _ in kombos:
        f_v = fakt.get("v", 0.0)
        vindval = ([None] + vind) if f_v > 0 else [None]
        for vf in vindval:
            # Varje kombination provas UTAN vind ocksa: utan vinden ar
            # varaktigheten langre och k_mod lagre -- ofta det varsta.
            fakt_har = dict(fakt)
            if vf is None:
                fakt_har["v"] = 0.0
            varakt = K.varaktighet_for_kombination(fakt_har, laster)
            kmod_b, kmod_v, kmod_f, kmod_sk = kmods(varakt)

            for fall in sno:
                fr, ix = bygg_uls()
                qv = (fakt_har["g"] * q_g
                      + fakt_har["s"] * L.linjelast(fall.s_vanster, cc))
                qh = (fakt_har["g"] * q_g
                      + fakt_har["s"] * L.linjelast(fall.s_hoger, cc))
                for e in ix["vanster"]:
                    fr.set_udl_projected(e, -qv)
                for e in ix["hoger"]:
                    fr.set_udl_projected(e, -qh)
                if vf is not None:
                    for e in ix["vanster"]:
                        fr.set_udl_local(e, -fakt_har["v"] * vf.w_vanster * cc)
                    for e in ix["hoger"]:
                        fr.set_udl_local(e, -fakt_har["v"] * vf.w_hoger * cc)
                fr.solve()

                vnamn = vf.namn if vf else "-"

                # Nocken -> forbandet
                _, N, V, M = fr.internal(ix["vanster"][-1])
                sk = Snittkraft(namn, fall.namn, vnamn, float(M[-1]),
                                float(N[-1]), float(V[-1]), varakt)
                snittkrafter.append(sk)

                # Kontakt i foget overfor bara TRYCK (handboken s. 290,
                # EN 1995-1-1 8.8.5). I lyftfallet ar N drag och fogen
                # gapar -- da far ingenting tillgodoraknas. Teckenet ar
                # ram.internal():s: N > 0 = drag.
                N_kontakt = (0.5 * abs(sk.N)
                             if sk.N < 0
                             and fb.get("kontakt_i_foget", False) else 0.0)
                skalade = skala_grupper(grupper, kmod_f, gamma_forb)
                gobj = [gg for _, gg, _ in skalade]
                sk_hb, sk_pl = _skivsatser(fb, skiva_mtrl, kmod_sk,
                                           gamma_skiva)
                skivor_dim = sk_pl if sk_pl is not None else sk_hb
                ktr = kontrollera(skivor_dim, gobj, sk.M, abs(sk.N), sk.V,
                                  N_kontakt, skarv=skarvmetod)
                if (varsta_nock is None
                        or ktr.utnyttjande_totalt > varsta_nock[0]):
                    ktr_hb = kontrollera(sk_hb, gobj, sk.M, abs(sk.N),
                                         sk.V, N_kontakt,
                                         skarv=skarvmetod)
                    varsta_nock = (ktr.utnyttjande_totalt, sk, ktr, ktr_hb,
                                   skalade, sk_hb, sk_pl, kmod_f)

                # Ledat forband enligt 5.3.7 (bara relevant utan styv nock)
                if not sysm["nock_styv"]:
                    led = ledad_nock(
                        sk.N, sk.V, fb["kolumner_liv"], fb["rader_liv"],
                        fb["cc_forbindare"],
                        grupper[1].kapacitet.F_v_Rd_kN(kmod_f, gamma_forb),
                        grupper[1].n_snitt, fb["skiva_t"],
                        fb["skiva_hojd_liv"],
                        (skiva_mtrl.draghallfasthet()
                         if skiva_mtrl.har_draghallfasthet
                         else skiva_mtrl.bojhallfasthet()),
                        skiva_mtrl.skivskjuvhallfasthet(),
                        kmod_sk, gamma_skiva,
                        taklutning_grader=g["taklutning"],
                        kant_ande=15.0 * grupper[1].forbindare.d,
                        forskjut_sida=float(
                            fb.get("sidoforskjutning", 0.0))
                        * fb["cc_forbindare"],
                        bas_andel=float(fb.get("rutnat_bas", 0.5)),
                        ankare=((balk.h / 2)
                                * __import__("math").tan(
                                    __import__("math").radians(
                                        g["taklutning"]))
                                if fb.get("rutnat_ankare", "")
                                == "flansvinkel" else None))
                    if (ledad_varsta is None
                            or led.utnyttjande > ledad_varsta.utnyttjande):
                        ledad_varsta = led
                        ledad_snitt = sk

                # Balken langs bada sparrarna. OBS: ix["hoger"] byggs av
                # ram.sadeltak som chain(apex, right) och gar alltsa
                # NOCK -> TAKFOT, medan ix["vanster"] gar takfot -> nock.
                # Snittlaget redovisas fran TAKFOTEN pa bada sidor, sa
                # hoger sidas s maste speglas.
                for sida in ("vanster", "hoger"):
                    s0 = 0.0
                    fran_nocken = (sida == "hoger")
                    for e in ix[sida]:
                        x, Ne, Ve, Me = fr.internal(e)
                        u = B.utnyttjande_falt(
                            balk, Me, Ve, Ne, L_ef, kmod_b, kmod_v,
                            dim["gamma_M_balk"], dim["beta_c"],
                            dim["E05_kvot"])
                        def lage(xi):
                            s = s0 + float(xi)
                            return L_sparre - s if fran_nocken else s

                        i = int(np.argmax(u))
                        if balksnitt is None or u[i] > balksnitt.utnyttjande:
                            balksnitt = Balksnitt(
                                namn, fall.namn, vnamn, sida,
                                lage(x[i]), float(Me[i]), float(Ne[i]),
                                float(Ve[i]), float(u[i]), varakt)
                        j = int(np.argmin(Me))
                        if hogmoment is None or Me[j] < hogmoment.M:
                            hogmoment = Balksnitt(
                                namn, fall.namn, vnamn, sida,
                                lage(x[j]), float(Me[j]), float(Ne[j]),
                                float(Ve[j]), float(u[j]), varakt)
                        s0 += float(x[-1])

                # Upplagen
                for sida, nod in (("vanster", ix["left"]),
                                  ("hoger", ix["right"])):
                    R = float(fr.reactions[3 * nod + 1])
                    kap = U.kapacitet(
                        balk, cfg.get("upplag", {}).get("L1", 45.0),
                        lage="and",
                        forstarkning=cfg.get("upplag", {}).get(
                            "forstarkning", False),
                        punktlast=cfg.get("upplag", {}).get(
                            "punktlast_over_stod", False),
                        y=cfg.get("upplag", {}).get("overhang_y", 0.0),
                        klimatklass=kk, varaktighet=varakt,
                        gamma_M=dim["gamma_M_balk"])
                    kvot = R / kap.F_Rd if kap.F_Rd > 0 else float("inf")
                    if kvot > R_max[sida][0]:
                        R_max[sida] = (kvot, (R, kap, sk, varakt))
                    H_max = max(H_max, abs(float(fr.reactions[3 * nod])))

    (_, dim_nock, kontroll, kontroll_hb, skalade, sk_hb, sk_pl,
     kmod_f_dim) = varsta_nock
    grupper_ut = [Grupp(gr.namn, gr.forbindare, gr.kapacitet, F_Rd,
                        gr.n_snitt, gg.n, gg, gr.intrangning)
                  for gr, gg, F_Rd in skalade]

    balkkontroller = B.kontrollera(
        balk, balksnitt.M, balksnitt.V, balksnitt.N, L_ef,
        *kmods(balksnitt.varaktighet)[:2], dim["gamma_M_balk"],
        dim["beta_c"], dim["E05_kvot"])

    upplag_kontroller = []
    for sida in ("vanster", "hoger"):
        kvot, info = R_max[sida]
        if info is None:
            continue
        R, kap, sk, varakt = info
        upplag_kontroller.append(B.Kontroll(
            namn=f"Upplagstryck {'vänster' if sida == 'vanster' else 'höger'} "
                 f"takfot",
            E_d=R, R_d=kap.F_Rd, enhet="kN", utnyttjande=kvot,
            referens=f"ETA ekv. 3-5 ({kap.formel.split(':')[0]}), k_mod "
                     f"{kap.k_mod} ({kap.k_mod_rad}, {varakt})",
            formel=f"R = {R:.2f} kN mot F_Rd = {kap.F_Rd:.2f} kN, "
                   f"L1 = {kap.detaljer['L1_eff']:.0f} mm",
            anmarkningar=list(kap.anmarkningar)))

    # -- 5. Nedbojning -----------------------------------------------------
    nedb = nedbojningsberakning(cfg, balk, q_g, sno, vind,
                                K_r.get("K_ser") if fjader else None)

    # -- 6. Metod, varningar, antaganden -----------------------------------
    metod = "i_planet" if sk_pl is not None else "handbok"
    varningar = sidostodskontroll(balk, g, hogmoment) + fb_varningar
    if metod == "handbok":
        varningar.append(
            f"{skiva_mtrl.namn} har ingen deklarerad draghållfasthet i "
            f"planet, så skivans momentkapacitet räknas med handbokens "
            f"f_m (plattböjning enligt EN 310). Välj osb3 eller p5, eller "
            f"lägg in f_t,0 ur skivans DoP.")
    elif skiva_mtrl.har_draghallfasthet and skiva_mtrl.dragriktning == "90":
        varningar.append(
            f"{skiva_mtrl.namn}: f_t,0 saknas, så skivans momentkontroll i "
            f"planet räknas med f_t,90 = "
            f"{skiva_mtrl.draghallfasthet():.1f} MPa (handboken 5.3.4.2 "
            f"s. 291) -- den svagare riktningen, konservativt oavsett "
            f"monteringsriktning.")
    if not vind:
        varningar.append(
            "Vindlast ingår inte: q_p eller c_pe-värdena saknas i "
            "[laster.vind]. Läs q_p ur EKS och c_pe ur EN 1991-1-4 "
            "tab. 7.4a för taklutningen, med båda tecknen.")
    if H_max > 0.5 and not sysm["dragband"]:
        varningar.append(
            f"Horisontalkraften i väggkrönet är {H_max:.1f} kN per takstol "
            f"och det finns inget dragband. Väggen och förbandet "
            f"takstol-väggkrön måste ta den kraften -- det kontrolleras "
            f"inte här.")

    if sysm["nock_styv"] and not skarvmetod:
        u_sk = kontroll.u_skarv_totalt
        varningar.append(
            f"Nockförbandet räknas enligt handbokens 5.3.4.1 (hela "
            f"spikbilden om fogen) och får {kontroll.utnyttjande_totalt:.3f}. "
            f"Räknat per HALVGRUPP -- vilket är den elastiska lösningen "
            f"för en skarv -- blir det {u_sk:.3f}, alltså "
            f"{u_sk / max(kontroll.utnyttjande_totalt, 1e-9):.1f} gånger "
            f"mer. Valet av handboksmetoden förutsätter att det finns "
            f"provningsunderlag bakom den. Se docs/ERRATA.md punkt 7.")

    if flanskval != TABELLKVALITET:
        varningar.append(
            f"Flänskvaliteten {flanskval} är vald, men ETA tab. 11/12 är "
            f"deklarerade enbart för {TABELLKVALITET} "
            f"(kvalitetskolumnen säger C30 på varje rad). M_k, EI, V_k "
            f"och N-värdena i biblioteket gäller alltså INTE för "
            f"{flanskval} -- de måste räknas om med ETA ekv. 1 och 2 på "
            f"tab. 4/5:s värden. Valet påverkar här bara förbandets "
            f"inbäddning och EA.")

    if nedb.overhojd_varning:
        varningar.append(nedb.overhojd_varning)
    # (spikbilden och stotfogen redovisas bland antagandena nedan)
    if ledad_varsta is not None and not sysm["nock_styv"]:
        varningar += list(ledad_varsta.varningar)

    u_upl = max((k.utnyttjande for k in upplag_kontroller), default=0.0)
    if u_upl > 1.0:
        varningar.append(
            f"Upplaget överskrids (utnyttjande {u_upl:.2f}). Det "
            f"redovisas separat och fäller inte takstolsbedömningen: "
            f"åtgärden är längre upplagslängd L1 eller livförstärkning "
            f"vid stödet, inte en annan balk.")

    antaganden = lastkallor + _antaganden(balk, skiva_mtrl, grupper_ut,
                                          dim, L_ef, flanskval,
                             L_sparre, metod, K_r, fjader, kmod_f_dim,
                             fb, dim_nock)

    # Med ledad nock ar det det LEDADE forbandets varsta fall som ar
    # dimensionerande -- inte den momentstyva kontrollens. run.py och
    # app.py redovisar dimensionerande.M/N/V intill den ledade nockens
    # egna tal, och de maste komma ur samma lastfall.
    if not sysm["nock_styv"] and ledad_snitt is not None:
        dim_nock = ledad_snitt

    if g["taklutning"] > 0:
        antaganden.append(
            f"Spikbilden tar hänsyn till den LODRÄTA stötfogen "
            f"(taklutning {g['taklutning']:.0f} grader): första spikraden "
            f"i varje kolonn läggs så att kantavståndet mot den kapade "
            f"änden är minst 15d (a3t:s övre gräns, tab. 8.2 -- i en "
            f"momentbelastad grupp pekar någon fognära spiks kraft alltid "
            f"mot änden). Gäller både momentstyv och ledad nock. Kolonner "
            f"under balkaxeln börjar längre från fogen; platt placering "
            f"hade lagt första spikarna i motstående sparre.")

    return Resultat(
        g_k=g_k, q_g=q_g, snofall=sno, vindfall=vind,
        snittkrafter=snittkrafter, dimensionerande=dim_nock, balk=balk,
        balksnitt=balksnitt, balkkontroller=balkkontroller,
        hogmoment=hogmoment, L_ef=L_ef, K_r=K_r,
        nocktyp="momentstyv" if sysm["nock_styv"] else "ledad",
        skivmaterial=skiva_mtrl, flanskvalitet=flanskval, metod=metod,
        skivor_handbok=sk_hb,
        skivor_i_planet=sk_pl, grupper=grupper_ut, kontroll=kontroll,
        kontroll_handbok=kontroll_hb, ledad=ledad_varsta,
        upplag_kontroller=upplag_kontroller, H_takfot=H_max,
        nedbojning=nedb, varningar=varningar, antaganden=antaganden)


def _e05_rad(dim, flanskval):
    """Antagandetexten for knackningens 5-percentil."""
    if not dim.get("E05_harledd"):
        return (f"EI_05 = {dim['E05_kvot']:.4f}*EI vid knäckning -- "
                f"ÖVERSTYRD i projektfilen, alltså ditt eget antagande.")
    kval = material.flanskvaliteter()[TABELLKVALITET]
    rad = material.en338(kval["en338"])
    return (f"EI_05 = {dim['E05_kvot']:.4f}*EI vid knäckning, HÄRLETT ur "
            f"SS-EN 338:2016 tab. 1 enligt ETA avsn. 1.2.4: E_0,05 = "
            f"{rad['E_0_05']:.0f} MPa för {kval['en338']} delat med ETA "
            f"tab. 5:s E_f = {kval['E_f']:.0f} MPa. Kvoten följer "
            f"TABELLENS kvalitet ({TABELLKVALITET}), för ETA tab. 11/12 "
            f"är deklarerade enbart för C30-flänsar.")


def _antaganden(balk, skiva_mtrl, grupper, dim, L_ef, flanskval, L_sparre,
                metod, K_r, fjader, kmod_f, fb, dim_nock):
    ut = ["Underlaget bygger på ETA 12/0018 utg. 2023-10-26 (RISE, dok. "
          "1220846, grund EAD 130367-00-0304). VALT 2026-08-18 efter "
          "kontroll: ingen nyare utgåva finns publicerad, men utfärdaren "
          "har inte bekräftat statusen och EOTA:s post ger 404. Se "
          "docs/ERRATA.md punkt 5b.",
          f"EA = {balk.EA(flanskval):.0f} kN ({flanskval}) är HÄRLETT ur "
          f"E_flans*A_flans + E_liv*A_liv. ETA 12/0018 deklarerar inte EA.",
          f"gamma_M = {dim['gamma_M_balk']} för balken -- handbokens eget "
          f"värde (s. 232); ETA:n deklarerar ingen.",
          f"Knäcklängd i planet {L_ef:.2f} m = "
          f"{dim['knacklangdsfaktor']:.2f} * sparrelängden {L_sparre:.2f} m.",
          _e05_rad(dim, flanskval),
          "Knäckning ur sparrens plan förutsätts förhindrad av sidostöd "
          "enligt ETA tab. 19 och kontrolleras separat.",
      
          f"k_mod för förbandet = sqrt(k_mod_skiva * k_mod_tra) enligt "
          f"EC5 2.3.2.1(2); i dimensionerande fallet "
          f"({dim_nock.varaktighet}) = {kmod_f:.3f}."]
    kf = int(fb.get("kolumner_flans", 1))
    if fjader and K_r:
        ut.append(
            f"Nockfjädern K_ser = {K_r['K_ser']:.0f} kNm/rad är löst "
            f"elastiskt i nockens VERKLIGA geometri (taklutning "
            f"{K_r['taklutning']:.0f} grader), med samma "
            f"koordinattransform som ritningen -- bild och siffra kommer "
            f"ur samma geometri. Platt (uppvikt) modell hade gett "
            f"{K_r['K_platt']:.0f}, en stel del {K_r['K_en_stel_del']:.0f}.")
    ut.append(
        "Flänsspikarna förutsätts zigzag-förskjutna minst 1d ur fiberlinjen "
        "(handboken s. 284): då gäller k_ef = 1 enligt EN 1995-1-1 "
        "8.3.1.1(8) och ingen radreduktion görs."
        + (f" kolumner_flans = {kf}: kolumnerna ligger med a2 = 5d "
           f"inbördes och varannan förskjuten en halv delning."
           if kf > 1 else ""))
    if fjader:
        ut.append(
            f"Nocken räknas med rotationsfjäder: K_ser = "
            f"{K_r['K_ser']:.0f} kNm/rad (EC5 tab. 7.1, rho_m = "
            f"{K_r['rho_m']:.0f} kg/m3 -- flänsens EN 338-medelvärde, "
            f"ett ANTAGANDE även för snittet mot skivan), K_u = 2/3*K_ser "
            f"= {K_r['K_u']:.0f} kNm/rad i brottgräns (EC5 2.2.2(2)).")
    else:
        ut.append("Nocken räknas HELT STYV (rotationsfjädern är avstängd). "
                  "Det överskattar nockmomentet och underskattar "
                  "fältmoment och nedböjning.")
    if skiva_mtrl.kontrollera_mot_dop:
        ut.append(f"{skiva_mtrl.namn}: värden ur handbokens exempel, inte "
                  f"ur en DoP.")
    else:
        ut.append(f"{skiva_mtrl.namn}: värden ur EN 12369-1. Kontrollera "
                  f"mot skivans DoP.")
    if metod == "i_planet":
        ut.append(f"Skivans momentkapacitet räknas med "
                  f"f_t,{skiva_mtrl.dragriktning} i planet; handbokens "
                  f"f_m (plattböjning) redovisas parallellt. Skivans egna "
                  f"kontroller får skivans eget k_mod -- inte förbandets "
                  f"sqrt-mix, som bara gäller förbindarna.")
    for gr in grupper:
        ut.append(f"{gr.namn}: F_v,Rk = {gr.kapacitet.F_v_Rk_kN:.3f} kN/"
                  f"snitt ur EC5 {gr.kapacitet.brottmod}, {gr.n_snitt} "
                  f"skjuvsnitt.")
        if gr.forbindare.f_u == 600.0:
            ut.append(f"{gr.forbindare.namn}: f_u = 600 MPa är EN 14592:s "
                      f"minimikrav; ett högre deklarerat värde ger högre "
                      f"kapacitet.")
    if fb.get("kontakt_i_foget", False):
        ut.append("Halva normalkraften tas av kontakt i fogen (handboken "
                  "s. 290, EN 1995-1-1 8.8.5). Förutsätter spalt högst "
                  "1,5/3,0 mm och gäller bara tryck.")
    ut.append("Spikgruppernas kapaciteter summeras, vilket förutsätter "
              "plastisk omlagring -- se metodanmärkningen i docs/ERRATA.md.")
    return ut


def jamfor_nock(cfg):
    """
    Kor kedjan med momentstyv och med ledad nock och stallar nyckeltalen
    mot varandra. README:s poang: med dragband eller vindsbjalklag behovs
    den momentstyva nocken formodligen inte alls.
    """
    import copy
    ut = {}
    for typ, styv in (("momentstyv", True), ("ledad", False)):
        c = copy.deepcopy(cfg)
        c["system"]["nock_styv"] = styv
        ut[typ] = kor(c)
    return ut
