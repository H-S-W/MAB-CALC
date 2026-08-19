"""
Verifiering av input/material/skivor.toml.

Skivvardena kommer fran EN 12369-1 via tillverkarnas datablad. De har inga
egna formler att kontrolleras mot, som balkarna har, men de gar att
korsverifiera mot ETA 12/0018: ETA:ns k_mod och k_def for balkens
tvarkraft respektive skjuvdeformation ar hamtade ur EC5 tab. 3.1 och 3.2
for LIVMATERIALET, alltsa exakt samma rader som galler for en skiva av
samma material. Stammer de inte overens ar minst en av filerna fel avlast.

Referenser:
  EN 12369-1               karakteristiska varden OSB och spanskiva
  EN 1995-1-1 tab. 3.1/3.2 k_mod och k_def
  ETA 12/0018 tab. 17/18   samma varden for balkens liv
"""

import tomllib
from pathlib import Path

import pytest

MATERIAL = Path(__file__).parent.parent / "input" / "material"
SKIVOR = tomllib.load(open(MATERIAL / "skivor.toml", "rb"))
BALKAR = tomllib.load(open(MATERIAL / "balkar.toml", "rb"))

VARAKTIGHETER = ["permanent", "lang", "medel", "kort", "momentan"]


def intervall_index(skiva, t):
    """Vilket tjockleksintervall en skivtjocklek t hamnar i.

    Intervallen i EN 12369-1 skrivs ">6-10", ">10-18" osv, dvs ovre gransen
    ingar i intervallet. En 18 mm skiva hor till ">10-18", inte ">18-25".

    En post dar tjocklek_min == tjocklek_max ar ingen tabell utan en ENDA
    tjocklek, sa som plywoodposten som bara har handbokens 18 mm. Da kravs
    exakt traff.
    """
    for i, (lo, hi) in enumerate(zip(skiva["tjocklek_min"],
                                     skiva["tjocklek_max"])):
        if lo == hi:
            if t == lo:
                return i
        elif lo < t <= hi:
            return i
    raise ValueError(f"{t} mm ligger utanfor tabellen for {skiva['namn']}")


# ---------------------------------------------------------------------------
# Korsverifiering mot ETA 12/0018
# ---------------------------------------------------------------------------

def test_kmod_stammer_med_eta_tabell_17():
    """
    ETA 12/0018 tab. 17 ger k_mod for balkens tvarkraft, som bars av livet.
    De vardena ska vara identiska med EC5 tab. 3.1 for samma skivmaterial.

    Om det har testet gar sonder har antingen skivor.toml eller balkar.toml
    lasts av fel -- eller sa har ETA:n andrats.
    """
    eta = BALKAR["kmod"]["tvarkraft"]
    par = [("osb3", "kk1", "osb_p7_kk1"), ("osb3", "kk2", "osb_p7_kk2"),
           ("p5", "kk1", "p5_kk1"),       ("p5", "kk2", "p5_kk2")]
    for skiva, kk, eta_nyckel in par:
        for v in VARAKTIGHETER:
            assert SKIVOR["kmod"][skiva][kk][v] == eta[eta_nyckel][v], \
                f"{skiva} {kk} {v}: skivor.toml mot ETA tab. 17"


def test_kdef_stammer_med_eta_tabell_18():
    """Samma korsverifiering for k_def, EC5 tab. 3.2 mot ETA tab. 18."""
    eta = BALKAR["kdef"]["skjuvning"]
    assert SKIVOR["kdef"]["osb3"]["kk1"] == eta["osb_p7_kk1"]
    assert SKIVOR["kdef"]["osb3"]["kk2"] == eta["osb_p7_kk2"]
    assert SKIVOR["kdef"]["p5"]["kk1"] == eta["p5_kk1"]
    assert SKIVOR["kdef"]["p5"]["kk2"] == eta["p5_kk2"]


def test_livmaterialen_i_eta_finns_som_skivor():
    """
    ETA avsn. 2.1: livet bestar av OSB/3 eller spanskiva P5 eller P7. De tva
    forsta ska finnas i skivbiblioteket, eftersom samma material anvands
    bade som liv i balken och som skiva i forbandet.
    """
    assert "osb3" in SKIVOR["skiva"]
    assert "p5" in SKIVOR["skiva"]


# ---------------------------------------------------------------------------
# Intern konsistens i skivtabellerna
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nyckel", ["osb3", "p5", "plywood_handbok"])
def test_tjockleksintervallen_hanger_ihop(nyckel):
    """
    Intervallen ska vara sammanhangande och vaxande. lo == hi tillats och
    betyder en enda exakt tjocklek, se intervall_index.
    """
    s = SKIVOR["skiva"][nyckel]
    lo, hi = s["tjocklek_min"], s["tjocklek_max"]
    assert len(lo) == len(hi)
    for i in range(len(lo)):
        assert lo[i] <= hi[i]
        if i:
            assert lo[i] == hi[i-1], "glapp eller overlapp mellan intervall"


def test_plywoodposten_ar_en_enda_tjocklek():
    """
    Plywoodposten ar avsiktligt bara handbokens 18 mm, inte en tabell over
    tjocklekar. EN 12369-2 ger inte generiska plywoodvarden -- de beror pa
    skivans uppbyggnad och maste hamtas ur DoP. Uppslagning pa nagon annan
    tjocklek ska darfor faila, inte tysta ge 18 mm-vardena.
    """
    s = SKIVOR["skiva"]["plywood_handbok"]
    assert intervall_index(s, 18) == 0
    for t in (12, 15, 21, 24):
        with pytest.raises(ValueError):
            intervall_index(s, t)


@pytest.mark.parametrize("nyckel", ["osb3", "p5", "plywood_handbok"])
def test_alla_kolumner_har_lika_manga_varden(nyckel):
    """Varje hallfasthets- och styvhetsrad ska ha ett varde per intervall."""
    s = SKIVOR["skiva"][nyckel]
    n = len(s["tjocklek_min"])
    for grupp in ("hallfasthet", "styvhet"):
        for namn, v in s.get(grupp, {}).items():
            if isinstance(v, list):
                assert len(v) == n, f"{nyckel}.{grupp}.{namn}"


@pytest.mark.parametrize("nyckel", ["osb3", "p5"])
def test_hallfastheten_avtar_med_tjockleken(nyckel):
    """
    EN 12369-1 ger lagre hallfasthet for tjockare skivor. Ingen rad far oka
    med tjockleken -- det fangar en kastad siffra eller en omvand kolumn.
    """
    for namn, v in SKIVOR["skiva"][nyckel]["hallfasthet"].items():
        if isinstance(v, list):
            assert v == sorted(v, reverse=True), f"{nyckel}.{namn}: {v}"


@pytest.mark.parametrize("nyckel", ["osb3", "p5"])
def test_tryck_ar_starkare_an_drag_i_planet(nyckel):
    """
    Bade OSB och spanskiva tar mer tryck an drag i skivans plan. Kvoten
    ligger runt 1.4-1.6 for OSB och 1.3-1.5 for P5.
    """
    h = SKIVOR["skiva"][nyckel]["hallfasthet"]
    drag = h["f_t_0"] if nyckel == "osb3" else h["f_t"]
    tryck = h["f_c_0"] if nyckel == "osb3" else h["f_c"]
    for ft, fc in zip(drag, tryck):
        assert 1.2 <= fc / ft <= 1.8


def test_osb_ar_starkare_i_huvudriktningen():
    """0 = huvudriktning ska genomgaende vara starkare an 90 = tvars."""
    h = SKIVOR["skiva"]["osb3"]["hallfasthet"]
    for a, b in (("f_m_0", "f_m_90"), ("f_t_0", "f_t_90"),
                 ("f_c_0", "f_c_90")):
        for v0, v90 in zip(h[a], h[b]):
            assert v0 > v90


def test_18_mm_hamnar_i_mellersta_intervallet():
    """
    18 mm ar den tjocklek handboken anvander. Den ska hamna i ">10-18",
    inte i ">18-25" -- en klassisk av-med-ett i den har typen av tabell.
    """
    assert intervall_index(SKIVOR["skiva"]["osb3"], 18) == 1
    assert intervall_index(SKIVOR["skiva"]["p5"], 18) == 1
    # och 18.1 mm ska hamna i nasta intervall
    assert intervall_index(SKIVOR["skiva"]["osb3"], 18.1) == 2


def test_varden_for_18_mm_osb3():
    """
    Last fast de varden som faktiskt kommer att anvandas for 18 mm OSB/3,
    sa att en andring i tabellen syns som ett trasigt test och inte som ett
    tyst andrat dimensioneringsresultat.

    EN 12369-1 via MEDITE SMARTPLY OSB3 datablad, tab. 2, intervall >10-18.
    """
    s = SKIVOR["skiva"]["osb3"]
    i = intervall_index(s, 18)
    h, e = s["hallfasthet"], s["styvhet"]
    assert (h["f_m_0"][i], h["f_m_90"][i]) == (16.4, 8.2)
    assert (h["f_t_0"][i], h["f_t_90"][i]) == (9.4, 7.0)
    assert (h["f_c_0"][i], h["f_c_90"][i]) == (15.4, 12.7)
    assert (h["f_v"][i], h["f_r"][i]) == (6.8, 1.0)
    assert (e["E_ct_0"][i], e["G_v"][i]) == (3800, 1080)


def test_varden_for_18_mm_p5():
    """UNILIN construction manual s. 3 tab. 2, intervall >10-18."""
    s = SKIVOR["skiva"]["p5"]
    i = intervall_index(s, 18)
    h = s["hallfasthet"]
    assert (h["f_m"][i], h["f_t"][i], h["f_c"][i]) == (13.3, 8.5, 11.8)
    assert (h["f_v"][i], h["f_r"][i]) == (6.5, 1.7)
    assert s["styvhet"]["E_m"][i] == 3300


def test_osb_livets_e_modul_forklarar_etans_troghetsradie():
    """
    ETA:ns i_y avtar med balkhojden eftersom livets area rakans med i A utan
    att bidra namnvart till I_y. Effektens storlek styrs av kvoten
    E_liv/E_flans. Med EN 12369-1:s E_ct_0 = 3800 MPa for OSB/3 och ETA
    tab. 5:s E_f = 13000 MPa for C30+ blir kvoten ca 0.29, vilket ar den
    storleksordning som reproducerar ETA:ns egna i_y-varden.

    Testet knyter ihop de tva databaserna och skulle fanga om E-modulen
    lastes av en faktor tio fel.
    """
    i = intervall_index(SKIVOR["skiva"]["osb3"], 10)
    E_liv = SKIVOR["skiva"]["osb3"]["styvhet"]["E_ct_0"][i]
    E_flans = BALKAR["flans"]["C30plus"]["E_f"]
    assert 0.2 <= E_liv / E_flans <= 0.4


# ---------------------------------------------------------------------------
# Plywood: handbokens exempelvarden
# ---------------------------------------------------------------------------

def test_plywoodvardena_ar_handbokens():
    """
    De varden projektets handbokstester ar lasta mot: f_m,k = 22.5 MPa och
    f_v,k = 3.0 MPa for 18 mm plywood, exempel 5.3.4.1.
    """
    s = SKIVOR["skiva"]["plywood_handbok"]
    assert s["hallfasthet"]["f_m_0"] == [22.5]
    assert s["hallfasthet"]["f_v"] == [3.0]
    assert s["kontrollera_mot_dop"] is True


def test_plywood_kmod_medel_ar_handbokens_0_8():
    """Handboken raknar med k_mod = 0.8 for medellang last i 5.3.4.1."""
    assert SKIVOR["kmod"]["plywood_handbok"]["kk1"]["medel"] == 0.80


def test_osb_har_hogre_skivskjuvhallfasthet_an_handbokens_plywood():
    """
    En konsekvens som ar latt att missa: OSB/3 har f_v = 6.8 MPa mot
    handbokens plywoodvarde 3.0 MPa. I skjuvkontrollen av skivan langs
    flansen ar OSB alltsa mer an dubbelt sa stark. Materialvalet slar
    darfor olika i momentkontrollen och i skjuvkontrollen.
    """
    osb = SKIVOR["skiva"]["osb3"]
    i = intervall_index(osb, 18)
    assert osb["hallfasthet"]["f_v"][i] > \
        2 * SKIVOR["skiva"]["plywood_handbok"]["hallfasthet"]["f_v"][0]


# ---------------------------------------------------------------------------
# k_mod och k_def, ordning mellan materialen
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nyckel", ["osb3", "p5", "plywood_handbok"])
def test_kmod_vaxer_med_kortare_lastvaraktighet(nyckel):
    for kk in ("kk1", "kk2"):
        v = [SKIVOR["kmod"][nyckel][kk][x] for x in VARAKTIGHETER]
        assert v == sorted(v), f"{nyckel} {kk}: {v}"


@pytest.mark.parametrize("nyckel", ["osb3", "p5", "plywood_handbok"])
def test_klimatklass_2_ar_aldrig_battre_an_klimatklass_1(nyckel):
    for v in VARAKTIGHETER:
        assert SKIVOR["kmod"][nyckel]["kk2"][v] <= \
            SKIVOR["kmod"][nyckel]["kk1"][v]
    assert SKIVOR["kdef"][nyckel]["kk2"] >= SKIVOR["kdef"][nyckel]["kk1"]


def test_p5_kryper_mer_an_osb_som_kryper_mer_an_plywood():
    """
    k_def: plywood 0.80, OSB/3 1.50, P5 2.25 i klimatklass 1. Ordningen ar
    densamma i klimatklass 2. Det ar den avvagning materialvalet handlar om
    -- P5 har hogre tvarkraftskapacitet men kryper tre ganger mer.
    """
    for kk in ("kk1", "kk2"):
        assert (SKIVOR["kdef"]["plywood_handbok"][kk]
                < SKIVOR["kdef"]["osb3"][kk]
                < SKIVOR["kdef"]["p5"][kk])


@pytest.mark.parametrize("nyckel", ["osb3", "p5", "plywood_handbok"])
def test_partialkoefficienten_ar_1_20_for_skivmaterial(nyckel):
    """EN 1995-1-1 tab. 2.3: gamma_M = 1.20 for skivmaterial."""
    assert SKIVOR["gamma_M"][nyckel] == 1.20
