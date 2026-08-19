"""
Uppslagning i materialbiblioteken.

Modulen innehaller INGA materialvarden. Allt lases ur TOML-filerna i
input/material/, som ar de filer du sjalv styr:

    balkar.toml       deklarerade varden ur Masonite Beams ETA 12/0018
    skivor.toml       karakteristiska varden ur EN 12369-1, plus plywood
    forbindare.toml   forbindarnas egna egenskaper

Vill du gora en balk eller en skiva otillganglig for programmet, ta bort
den ur biblioteket. Vill du lagga till en, lagg in raden dar. Koden har
inga hardkodade alternativ.

Partialkoefficienter och modifieringsfaktorer kommer ocksa darifran:
k_mod och k_def for BALKEN ur ETA tab. 17/18, for SKIVOR ur EC5 tab.
3.1/3.2. Det ar inte samma varden, och tvarkraft har egna lagre varden an
bojning -- se docstringarna nedan.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

MATERIAL_DIR = Path(__file__).parent.parent / "input" / "material"

VARAKTIGHETER = ("permanent", "lang", "medel", "kort", "momentan")

# Livmaterialets nyckel skiljer sig mellan filerna. balkar.toml grupperar
# balkarna pa "osb"/"spanskiva", ETA:ns faktortabeller pa "osb_p7"/"p5" och
# skivbiblioteket pa "osb3"/"p5".
_LIV = {
    "osb":       {"faktor": "osb_p7", "skiva": "osb3"},
    "spanskiva": {"faktor": "p5",     "skiva": "p5"},
}


def _las(filnamn):
    with open(MATERIAL_DIR / filnamn, "rb") as fh:
        return tomllib.load(fh)


BALKAR_DATA = _las("balkar.toml")
SKIVOR_DATA = _las("skivor.toml")
FORBINDARE_DATA = _las("forbindare.toml")
NEDBOJNING_DATA = _las("nedbojningskrav.toml")

# Regelverket ligger i en egen katalog: det ar forfattningstext, inte
# materialdata, och har en annan upphovsrattslig status (fri enligt 9 §
# upphovsrattslagen).
with open(MATERIAL_DIR.parent / "regelverk" / "bfs2024-6.toml", "rb") as _fh:
    BFS_DATA = tomllib.load(_fh)


def nedbojningskrav(nyckel: str, del_: str = "tak") -> dict:
    """
    Tillaten nedbojning for en byggnadstyp, handboken s. 229 via
    input/material/nedbojningskrav.toml. Vardena ar n i L/n; 0 betyder
    att handboken inte anger nagot krav for den kombinationen.

    del_  "tak" for takkonstruktioner, "bjalklag" for underram i
          ramverkstakstol och vindsbjalklag. OBS att bjalklagskraven
          bara tacker NEDBOJNING -- svikt och vibrationer (EC5 7.3)
          kontrolleras inte av programmet.
    """
    if del_ not in NEDBOJNING_DATA:
        raise KeyError(f"{del_!r} finns inte -- välj 'tak' eller 'bjalklag'")
    rader = NEDBOJNING_DATA[del_]
    if nyckel not in rader:
        raise KeyError(
            f"{nyckel!r} finns inte bland {del_}-kraven. Tillgängliga: "
            f"{', '.join(rader)}")
    return rader[nyckel]


def nedbojningskravnamn(del_: str = "tak") -> list:
    """Nycklarna i biblioteket, for granssnittens dropdownar."""
    return sorted(NEDBOJNING_DATA.get(del_, {}))

GAMMA_M_FORBAND = FORBINDARE_DATA["metadata"]["gamma_M_forband"]


def _kk(klimatklass):
    if klimatklass not in (1, 2):
        raise ValueError(
            f"klimatklass {klimatklass}: ETA 12/0018 avsn. 2 begränsar "
            f"produkten till klimatklass 1 och 2")
    return f"kk{klimatklass}"


def _varaktighet(v):
    if v not in VARAKTIGHETER:
        raise ValueError(f"okänd lastvaraktighet {v!r}, välj bland "
                         f"{', '.join(VARAKTIGHETER)}")
    return v


# ---------------------------------------------------------------------------
# Balk
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Balk:
    """
    Deklarerade varden ur ETA 12/0018 tab. 11 eller 12, plus den geometri
    som gar att harleda ur tab. 1 och tabellrubrikerna.

    Alla kapaciteter ar KARAKTERISTISKA. Dimensionerande varden fas genom
    att multiplicera med k_mod och dela med gamma_M -- se k_mod_bojning()
    och k_mod_tvarkraft(), som INTE ar samma faktor.
    """
    namn: str
    serie: str
    liv: str                # "osb" eller "spanskiva"
    h: float                # mm
    h_flans: float          # mm
    b_flans: float          # mm
    t_liv: float            # mm
    sidostod_max: float     # mm, ETA tab. 19
    M_k: float              # kNm
    EI: float               # kNm2
    V_k: float              # kN
    GA: float               # kN
    i_x: float              # m
    i_y: float              # m
    N_ck: float             # kN
    _N_tk: float            # kN, -1 = saknas i ETA:n

    @property
    def h_liv(self) -> float:
        """Fri livhojd mellan flansarna [mm]."""
        return self.h - 2 * self.h_flans

    @property
    def c_flans(self) -> float:
        """
        c/c mellan flansarnas tyngdpunkter [mm]. Det ar handbokens x-matt
        i spikgruppen: 253 mm for en H300, se handboken s. 288.
        """
        return self.h - self.h_flans

    @property
    def A_flans(self) -> float:
        """Bada flansarnas sammanlagda area [mm2]."""
        return 2 * self.h_flans * self.b_flans

    @property
    def A_liv(self) -> float:
        return self.t_liv * self.h_liv

    @property
    def N_tk(self) -> float:
        """
        Karakteristisk dragkapacitet [kN].

        Hojer fel for HB-balkar med OSB-liv, dar ETA tab. 11 upprepar
        M_k-kolumnen i N_tk-kolumnen. Se docs/ERRATA.md punkt 4.
        """
        if self._N_tk < 0:
            raise ValueError(
                f"{self.namn}: dragkapaciteten saknas. ETA 12/0018 tab. 11 "
                f"anger för HB-serien med OSB-liv samma tal i N_tk som i "
                f"M_k, vilket är en klippmiss -- se docs/ERRATA.md punkt 4. "
                f"Välj spånskiveliv ({self.namn}s), en annan serie, eller "
                f"begär värdet från Masonite Beams eller RISE.")
        return self._N_tk

    @property
    def har_dragkapacitet(self) -> bool:
        return self._N_tk >= 0

    def EA(self, flanskvalitet="C30plus") -> float:
        """
        Axialstyvhet [kN]. HARLETT, inte deklarerat.

        ETA:n ger EI och GA men inte EA. Harledningen ar

            EA = E_flans * A_flans + E_liv * A_liv

        med E_flans ur ETA tab. 5 och E_liv ur EN 12369-1 for
        livmaterialet. Flansarna star for det mesta -- for en H300 med
        OSB-liv ger livet knappt 12 % av EA -- sa osakerheten i E_liv far
        liten effekt.

        Vardet ska redovisas som ett antagande i rapporten. Det anvands
        bara i ramanalysens axialstyvhet, dar det har liten inverkan pa
        snittkrafterna i en tvaledsram.
        """
        E_flans = BALKAR_DATA["flans"][flanskvalitet]["E_f"]
        E_liv = _E_livmaterial(self.liv, self.t_liv)
        return (E_flans * self.A_flans + E_liv * self.A_liv) / 1000.0

    def sidostod_ok(self, avstand_mm: float) -> bool:
        """
        Uppfyller ett givet sidostodsavstand ETA tab. 19?

        ETA annex 3: den deklarerade momentkapaciteten M_k galler bara nar
        TRYCKFLANSEN ar sidostodd med hogst det avstandet. Det ar villkoret
        som ersatter en vippningsberakning -- men det maste da provas mot
        den flans som faktiskt ar tryckt, vilket i ett omrade med negativt
        moment ar underflansen.
        """
        return avstand_mm <= self.sidostod_max


def _E_livmaterial(liv: str, t: float) -> float:
    """
    E-modul for livmaterialet [MPa] ur skivbiblioteket.

    OSB har separata varden for drag och tryck i planet (E_ct_0), vilket ar
    det relevanta for axialstyvhet. EN 12369-1 ger for spanskiva bara
    bojmodulen E_m, sa den anvands da. Skillnaden ar liten i sammanhanget,
    se Balk.EA().
    """
    nyckel = _LIV[liv]["skiva"]
    s = SKIVOR_DATA["skiva"][nyckel]
    i = _tjockleksindex(s, t)
    styvhet = s["styvhet"]
    return styvhet["E_ct_0"][i] if "E_ct_0" in styvhet else styvhet["E_m"][i]


def balk(namn: str) -> Balk:
    """Slar upp en balk pa beteckning, t.ex. "H300" eller "HM400s"."""
    for livnyckel, rader in BALKAR_DATA["balk"].items():
        if namn in rader:
            return _bygg_balk(namn, livnyckel, rader[namn])
    raise KeyError(
        f"{namn!r} finns inte i balkbiblioteket. Tillgängliga: "
        f"{', '.join(sorted(balknamn()))}")


def _bygg_balk(namn, livnyckel, rad) -> Balk:
    serie = BALKAR_DATA["serie"][rad["serie"]]
    return Balk(namn=namn, serie=rad["serie"], liv=livnyckel, h=rad["h"],
                h_flans=serie["h_flans"], b_flans=serie["b_flans"],
                t_liv=serie["t_liv"], sidostod_max=serie["sidostod_max"],
                M_k=rad["M_k"], EI=rad["EI"], V_k=rad["V_k"], GA=rad["GA"],
                i_x=rad["i_x"], i_y=rad["i_y"], N_ck=rad["N_ck"],
                _N_tk=rad["N_tk"])


def balknamn(liv=None, serie=None) -> list:
    """
    Alla balkbeteckningar i biblioteket, valfritt filtrerade.

    liv    "osb" eller "spanskiva"
    serie  "H", "HM", "HI" eller "HB"
    """
    ut = []
    for livnyckel, rader in BALKAR_DATA["balk"].items():
        if liv and livnyckel != liv:
            continue
        for namn, rad in rader.items():
            if serie and rad["serie"] != serie:
                continue
            ut.append(namn)
    return ut


def balkar(liv=None, serie=None) -> list:
    """Samma som balknamn() men returnerar Balk-objekt sorterade pa hojd."""
    return sorted((balk(n) for n in balknamn(liv, serie)),
                  key=lambda b: (b.serie, b.h))


# ---------------------------------------------------------------------------
# k_mod och k_def for BALKEN, ETA tab. 17 och 18
# ---------------------------------------------------------------------------

def k_mod_bojning(klimatklass: int, varaktighet: str) -> float:
    """
    k_mod for bojning, upplagstryck och axialkraft, ETA tab. 17.
    Samma varden i klimatklass 1 och 2.
    """
    return BALKAR_DATA["kmod"]["bojning_upplag_axial"][
        _kk(klimatklass)][_varaktighet(varaktighet)]


def k_mod_tvarkraft(liv: str, klimatklass: int, varaktighet: str) -> float:
    """
    k_mod for TVARKRAFT, ETA tab. 17. Egna, lagre varden an bojningens,
    och de beror pa livmaterialet eftersom det ar livet som bar
    tvarkraften. Vid medellang last i klimatklass 1 ar det 0,70 for
    OSB-liv och 0,65 for P5 -- inte bojningens 0,80.

    Enligt ETA:ns fotnot galler de har vardena aven for UPPLAGSKAPACITET i
    fallet med punktlast ovanifran utan forstarkning, vid h >= 250 for
    andupplag och h >= 300 for innerupplag.
    """
    nyckel = f"{_LIV[liv]['faktor']}_{_kk(klimatklass)}"
    return BALKAR_DATA["kmod"]["tvarkraft"][nyckel][_varaktighet(varaktighet)]


def k_def_bojning(klimatklass: int) -> float:
    """k_def for boj- och axialdeformation, ETA tab. 18."""
    return BALKAR_DATA["kdef"]["bojning_axial"][_kk(klimatklass)]


def k_def_skjuvning(liv: str, klimatklass: int) -> float:
    """
    k_def for SKJUVDEFORMATION, ETA tab. 18. Betydligt storre an
    bojningens: 1,50 for OSB och 2,25 for P5 i klimatklass 1, mot 0,60 for
    bojningen. Nedbojning i bruksgranstillstand maste darfor delas i en
    bojdel och en skjuvdel med olika krypfaktor.
    """
    nyckel = f"{_LIV[liv]['faktor']}_{_kk(klimatklass)}"
    return BALKAR_DATA["kdef"]["skjuvning"][nyckel]


# ---------------------------------------------------------------------------
# Skivmaterial
# ---------------------------------------------------------------------------

def _tjockleksindex(skiva: dict, t: float) -> int:
    """
    Vilket tjockleksintervall t hamnar i. Intervallen i EN 12369-1 skrivs
    ">10-18" osv, dvs den ovre gransen ingar.

    En post dar tjocklek_min == tjocklek_max ar en ENDA tjocklek och kraver
    exakt traff. Sa ar plywoodposten byggd, eftersom EN 12369-2 inte ger
    generiska plywoodvarden.
    """
    for i, (lo, hi) in enumerate(zip(skiva["tjocklek_min"],
                                     skiva["tjocklek_max"])):
        if (lo == hi and t == lo) or (lo < t <= hi):
            return i
    giltiga = ", ".join(
        f"{lo}-{hi}" for lo, hi in zip(skiva["tjocklek_min"],
                                       skiva["tjocklek_max"]))
    raise ValueError(
        f"{t} mm finns inte för {skiva['namn']}. Giltiga intervall: {giltiga}")


@dataclass(frozen=True)
class Skivmaterial:
    """
    Ett skivmaterial vid en bestamd tjocklek, med varden upplosta ur
    tjockleksintervallet.

    hallfasthet och styvhet ar dictar med de nycklar som finns for just det
    materialet. OSB har riktningsberoende varden med suffix _0 och _90,
    spanskiva ar isotrop i planet och har inga suffix. Anvand
    bojhallfasthet() och draghallfasthet() for att slippa bry dig om det.
    """
    nyckel: str
    namn: str
    t: float
    anisotrop: bool
    hallfasthet: dict
    styvhet: dict
    kontrollera_mot_dop: bool

    def bojhallfasthet(self) -> float:
        """
        f_m i huvudriktningen [MPa]. Det ar handbokens parameter for
        skivans momentkapacitet, men den ar uppmatt som PLATTBOJNING enligt
        EN 310 -- se draghallfasthet() och [metod] i skivor.toml.
        """
        return self.hallfasthet["f_m_0" if self.anisotrop else "f_m"]

    @property
    def _dragnyckel(self) -> str:
        return "f_t_0" if self.anisotrop else "f_t"

    @property
    def har_draghallfasthet(self) -> bool:
        """
        Om materialet har en deklarerad draghallfasthet i planet.

        EN 12369-1 ger f_t,0 for OSB och spanskiva. Handbokens plywood
        deklarerar f_t,90 = 7,0 MPa (exempel 5.3.4.2, s. 291) -- den
        SVAGARE riktningen, och darmed anvandbar konservativt oavsett
        at vilket hall skivan monteras.
        """
        return (self._dragnyckel in self.hallfasthet
                or (self.anisotrop and "f_t_90" in self.hallfasthet))

    @property
    def dragriktning(self) -> str:
        """"0" nar f_t,0 finns, "90" nar bara f_t,90 finns."""
        return "0" if self._dragnyckel in self.hallfasthet else "90"

    def draghallfasthet(self) -> float:
        """
        Draghallfasthet i skivans PLAN [MPa] -- parametern for bojning i
        planet, som i nockforbandet. f_t,0 om den finns; annars f_t,90,
        som ar svagare och darfor konservativ nar monteringsriktningen
        inte ar styrd. Vilken som anvands framgar av dragriktning.
        """
        if self._dragnyckel in self.hallfasthet:
            return self.hallfasthet[self._dragnyckel]
        if self.anisotrop and "f_t_90" in self.hallfasthet:
            return self.hallfasthet["f_t_90"]
        raise ValueError(
            f"{self.namn} har ingen deklarerad draghållfasthet i planet "
            f"({self._dragnyckel} eller f_t_90). Ta värdet ur skivans DoP "
            f"och lägg in det i skivor.toml, eller välj osb3 eller p5 där "
            f"EN 12369-1 ger det.")

    def tryckhallfasthet(self) -> float:
        nyckel = "f_c_0" if self.anisotrop else "f_c"
        if nyckel not in self.hallfasthet:
            raise ValueError(
                f"{self.namn} har ingen deklarerad tryckhållfasthet i planet "
                f"({nyckel}). Se draghallfasthet().")
        return self.hallfasthet[nyckel]

    def skivskjuvhallfasthet(self) -> float:
        """f_v, skjuvning i skivans plan [MPa]."""
        return self.hallfasthet["f_v"]

    @property
    def rho_k(self) -> float:
        """
        Karakteristisk densitet [kg/m3]. Behovs for halkantshallfastheten i
        plywood, ekv. 8.20. EN 12369-1 anger den inte for OSB och spanskiva
        -- deras halkantshallfasthet raknas i stallet ur tjockleken,
        ekv. 8.22, sa vardet behovs inte dar.
        """
        if "rho_k" not in self.hallfasthet:
            raise ValueError(
                f"{self.namn} har ingen deklarerad rho_k i biblioteket. "
                f"För OSB och spånskiva behövs den inte: EN 1995-1-1 "
                f"ekv. 8.22 räknar hålkantshållfastheten ur tjockleken.")
        return self.hallfasthet["rho_k"]


def skiva(nyckel: str, t: float) -> Skivmaterial:
    """
    Slar upp ett skivmaterial vid tjockleken t [mm].

    nyckel  "osb3", "p5" eller "plywood_handbok"
    """
    if nyckel not in SKIVOR_DATA["skiva"]:
        raise KeyError(
            f"{nyckel!r} finns inte i skivbiblioteket. Tillgängliga: "
            f"{', '.join(SKIVOR_DATA['skiva'])}")
    s = SKIVOR_DATA["skiva"][nyckel]
    i = _tjockleksindex(s, t)

    def losupp(grupp):
        return {namn: (v[i] if isinstance(v, list) else v)
                for namn, v in s.get(grupp, {}).items()}

    return Skivmaterial(nyckel=nyckel, namn=s["namn"], t=t,
                        anisotrop=s["anisotrop"],
                        hallfasthet=losupp("hallfasthet"),
                        styvhet=losupp("styvhet"),
                        kontrollera_mot_dop=s.get("kontrollera_mot_dop",
                                                  False))


def skivnamn() -> list:
    return list(SKIVOR_DATA["skiva"])


def visningsnamn_skiva(nyckel: str) -> str:
    """Skivans namn for redovisning, sa att granssnitt slipper na in i datat."""
    return SKIVOR_DATA["skiva"][nyckel]["namn"]


def k_mod_skiva(nyckel: str, klimatklass: int, varaktighet: str) -> float:
    """k_mod for skivmaterial, EC5 tab. 3.1."""
    return SKIVOR_DATA["kmod"][nyckel][_kk(klimatklass)][
        _varaktighet(varaktighet)]


def k_def_skiva(nyckel: str, klimatklass: int) -> float:
    """k_def for skivmaterial, EC5 tab. 3.2."""
    return SKIVOR_DATA["kdef"][nyckel][_kk(klimatklass)]


def gamma_M_skiva(nyckel: str) -> float:
    """gamma_M for skivmaterial, EC5 tab. 2.3."""
    return SKIVOR_DATA["gamma_M"][nyckel]


def skivbojning_dimensionerande() -> str:
    """
    Vilken hallfasthetsparameter som ar dimensionerande for skivans
    bojning i sitt eget plan: "i_planet" (f_t,0) eller "handbok" (f_m).
    Styrs av [metod] i skivor.toml. Se motiveringen dar.
    """
    return SKIVOR_DATA["metod"]["skivbojning_dimensionerande"]


# ---------------------------------------------------------------------------
# Forbindare
# ---------------------------------------------------------------------------

def forbindare(nyckel: str):
    """
    Slar upp en forbindare och returnerar ett
    forbindare_ec5.Forbindare-objekt. Kapaciteten raknas fram ur EC5
    8.2.2 -- den star inte i biblioteket.
    """
    from forbindare_ec5 import Forbindare

    if nyckel not in FORBINDARE_DATA["forbindare"]:
        raise KeyError(
            f"{nyckel!r} finns inte i förbindarbiblioteket. Tillgängliga: "
            f"{', '.join(FORBINDARE_DATA['forbindare'])}")
    rad = FORBINDARE_DATA["forbindare"][nyckel]
    return Forbindare(namn=rad["namn"], d=rad["d"], langd=rad["langd"],
                      f_u=rad["f_u"], typ=rad["typ"],
                      forborrning=rad["forborrning"],
                      F_ax_Rk=rad["F_ax_Rk"])


def forbindarnamn() -> list:
    return list(FORBINDARE_DATA["forbindare"])


def visningsnamn_forbindare(nyckel: str) -> str:
    return FORBINDARE_DATA["forbindare"][nyckel]["namn"]


def regelverk() -> dict:
    """BFS 2024:6, ur input/regelverk/bfs2024-6.toml."""
    return BFS_DATA


def gamma_d(sakerhetsklass: int) -> float:
    """Partialkoefficient for sakerhetsklass, BFS 2024:6 2 kap. 2 §."""
    try:
        return BFS_DATA["sakerhetsklass"][str(sakerhetsklass)]
    except KeyError:
        raise ValueError(
            f"sakerhetsklass {sakerhetsklass} finns inte -- välj 1, 2 eller 3")


def psi_sno(S_0: float) -> dict:
    """
    psi-faktorer for snolast, BFS 2024:6 tab. 3:6.

    Tabellen anger banden som "snozon 1 och 1,5", "snozon 2 och 2,5" och
    "snozon 3 och uppat". Ordet snozon definieras inte i forfattningen --
    att snozon n ar detsamma som S_0 = n kN/m2 ar HARLETT ur att kartans
    vardemangd sammanfaller med bandgranserna. Redovisas som antagande.
    """
    band = sorted(((v["S_0_max"], v) for n, v in
                   BFS_DATA["klimatlast"].items() if n.startswith("sno_zon")),
                  key=lambda p: p[0])
    for grans, rad in band:
        if S_0 <= grans + 1e-9:
            return rad
    return band[-1][1]


def psi(lasttyp: str) -> dict:
    """psi-faktorer for vind, temperatur och nyttig last pa yttertak."""
    if lasttyp in BFS_DATA["klimatlast"]:
        return BFS_DATA["klimatlast"][lasttyp]
    if lasttyp in BFS_DATA["nyttig_last"]:
        return BFS_DATA["nyttig_last"][lasttyp]
    raise ValueError(f"okänd lasttyp {lasttyp!r} i BFS 2024:6 tab. 3:5/3:6")


def terrangtyper() -> dict:
    """Tabell 4:4, BFS 2024:6 4 kap. 39 §."""
    return BFS_DATA["terrang"]


def terrang(typ: str) -> dict:
    t = BFS_DATA["terrang"]
    if str(typ) not in t:
        raise ValueError(
            f"terrangtyp {typ!r} finns inte -- välj {', '.join(t)} "
            f"(BFS 2024:6 tab. 4:4)")
    return t[str(typ)]


def vindkonstanter() -> dict:
    """rho, k_p och z0_ref ur BFS 2024:6 4 kap. 38 §."""
    return BFS_DATA["vind"]


def lastkombinationer() -> dict:
    """Tabell 3:1, brottgranstillstand."""
    return BFS_DATA["lastkombination"]


def flanskvaliteter() -> dict:
    """Flansdata ur ETA tab. 4 och 5, plus EN 338:s densitet."""
    return BALKAR_DATA["flans"]


def en338(klass: str) -> dict:
    """En rad ur SS-EN 338:2016 tab. 1."""
    try:
        return BALKAR_DATA["en338"][klass]
    except KeyError:
        raise ValueError(
            f"okänd hållfasthetsklass '{klass}' -- finns: "
            f"{', '.join(sorted(BALKAR_DATA['en338']))}")


def e05_kvot(flanskvalitet: str) -> float:
    """
    Kvoten E_0,05 / E_f for knackning.

    ETA 12/0018 avsn. 1.2.4: axialkraftskapaciteten ska raknas enligt EC5
    med hallfasthets- OCH STYVHETSVARDEN ur EN 338, och C30+ raknas som
    C30. Taljaren ar alltsa EN 338:s 5-percentil (8 000 MPa for C30),
    inte 2/3 av ETA:ns forhojda C30+-medelvarde.

    Namnaren ar ETA tab. 5:s E_f, for kvoten multipliceras med ETA:ns EI
    som ar byggd pa just det vardet (ekv. 2). Webbens andel av EI skalas
    med samma kvot, vilket ar nagot konservativt -- livmaterialet ar inte
    tra och tacks inte av EN 338.
    """
    kval = flanskvaliteter()[flanskvalitet]
    return en338(kval["en338"])["E_0_05"] / kval["E_f"]
