"""
Verifiering av input/material/balkar.toml mot ETA 12/0018.

Tabellvarden som ar avlasta for hand ur ett PDF-dokument maste laskas fast.
De har testerna kontrollerar de transkriberade varden mot ETA:ns EGNA
formler och mot interna monster i tabellerna, sa att en felskrivning inte
kan passera obemarkt.

Referens: Masonite Beams ETA 12/0018, 2023-10-26 (RISE), tab. 11 och 12
samt ekv. 6 och 7.
"""

import tomllib
from math import sqrt
from pathlib import Path

import pytest

TOML = Path(__file__).parent.parent / "input" / "material" / "balkar.toml"
CFG = tomllib.load(open(TOML, "rb"))

# (livtyp, ETA-ekvation for V_k, GA vid h=200, GA-lutning per mm)
LIV = [
    ("osb",       lambda h: 0.0674*h + 0.3, 1419, 10.8),   # ETA ekv. 6
    ("spanskiva", lambda h: 0.0647*h + 3.7, 1261,  9.6),   # ETA ekv. 7
]

ALLA = [(liv, namn, b)
        for liv, _, _, _ in LIV
        for namn, b in CFG["balk"][liv].items()]


def test_antal_balkar():
    """ETA tab. 11 och 12 har 4 serier x 9 hojder vardera."""
    assert len(CFG["balk"]["osb"]) == 36
    assert len(CFG["balk"]["spanskiva"]) == 36


@pytest.mark.parametrize("liv,namn,b", ALLA, ids=[f"{n}" for _, n, _ in ALLA])
def test_tvarkraft_stammer_med_eta_ekvation(liv, namn, b):
    """
    V_k = 0.0674*h + 0.3   for OSB/3-liv        (ETA ekv. 6)
    V_k = 0.0647*h + 3.7   for spanskiveliv P5  (ETA ekv. 7)

    Tabellvardena ar avrundade till 0.1 kN.
    """
    ekv = next(e for lv, e, _, _ in LIV if lv == liv)
    assert b["V_k"] == pytest.approx(ekv(b["h"]), abs=0.06)


@pytest.mark.parametrize("liv,namn,b", ALLA, ids=[f"{n}" for _, n, _ in ALLA])
def test_momentkapaciteten_stammer_med_eta_ekvation_1(liv, namn, b):
    """
    ETA ekv. 1:  M_k = f_m,k * I_eff/(h/2) * k_h  med k_h = (300/h)^0,25

    I_eff gar att fa ur den tabellerade bojstyvheten, eftersom ekv. 2 sager
    EI = E_f * I_eff. Da kan M_k i tab. 11/12 raknas fram ur EI i SAMMA
    tabell tillsammans med f_m,k ur tab. 4 och E_f ur tab. 5 -- fyra
    tabeller och tva ekvationer som maste ga ihop.

    Overensstammelsen ar 1,28 % som sämst och 0,16 % i median over alla 72
    balkar. Avvikelsen forklaras av att bade EI och M_k ar avrundade i
    trycket. Toleransen ar satt till 2 %, vilket ryms med marginal men anda
    fangar en kastad siffra -- en sadan flyttar vardet tiotals procent.

    Testet bekraftar ocksa att k_h REDAN ar inbakad i tabellernas M_k. Den
    far inte laggas till en andra gang i balk.M_Rd().
    """
    E_f = CFG["flans"]["C30plus"]["E_f"]
    f_m_k = CFG["flans"]["C30plus"]["f_m_k"]

    I_eff = b["EI"] * 1e9 / E_f                  # kNm2 -> Nmm2 -> mm4
    k_h = (300 / b["h"]) ** 0.25
    M_k = f_m_k * I_eff / (b["h"] / 2) * k_h / 1e6

    assert M_k == pytest.approx(b["M_k"], rel=0.02)


def test_storleksfaktorn_k_h_ar_ett_vid_300_mm():
    """
    f_m,k i tab. 4 ar angiven for balkhojd 300 mm, och k_h = (300/h)^0,25
    blir da precis 1,0. Det ar referenspunkten hela ekv. 1 hanger pa.
    """
    assert (300 / 300) ** 0.25 == 1.0
    assert (300 / 500) ** 0.25 < 1.0             # hogre balk -> lagre f_m
    assert (300 / 200) ** 0.25 > 1.0


@pytest.mark.parametrize("liv,namn,b", ALLA, ids=[f"{n}" for _, n, _ in ALLA])
def test_skjuvstyvhet_ar_linjar_i_balkhojden(liv, namn, b):
    """GA vaxer linjart med h i bada ETA-tabellerna."""
    _, _, GA0, lutning = next(x for x in LIV if x[0] == liv)
    assert b["GA"] == pytest.approx(GA0 + (b["h"] - 200) * lutning, abs=0.5)


@pytest.mark.parametrize("liv,namn,b", ALLA, ids=[f"{n}" for _, n, _ in ALLA])
def test_troghetsradie_sidled_rimlig(liv, namn, b):
    """
    i_y styrs av flansbredden: i_y ~ b_flans/sqrt(12). Kvoten ligger i ETA:s
    tabeller mellan 0.88 och 1.03 av det vardet.

    Den avviker at bada hallen eftersom livets area rakans med i A utan att
    bidra namnvart till I_y (drar nedat, mest for smala flansar och hoga
    balkar) medan tabellen ar avrundad till tre decimaler, vilket pa vardena
    0.012-0.014 ar en grov avrundning (drar bada hallen).

    Testet ar en rimlighetskontroll som fangar en felskriven siffra, inte en
    reproduktion av ETA:ns tvarsnittsberakning. Att traffa vardena exakt
    kraver E-modulen for livmaterialet, som ETA:n inte deklarerar. i_y
    anvands inte av nagon kontroll i det har projektet -- takstolens
    sidostabilitet styrs av kravet pa sidostod i ETA tab. 19, inte av i_y.
    Kolumnen bars med for fullstandighetens skull.
    """
    b_flans = CFG["serie"][b["serie"]]["b_flans"]
    referens = b_flans / sqrt(12) / 1000
    assert 0.86 * referens <= b["i_y"] <= 1.05 * referens


@pytest.mark.parametrize("liv", ["osb", "spanskiva"])
def test_troghetsradie_sidled_avtar_med_hojden(liv):
    """Livets area dilluerar i_y -> i_y far aldrig oka med h inom en serie."""
    per_serie = {}
    for b in CFG["balk"][liv].values():
        per_serie.setdefault(b["serie"], []).append((b["h"], b["i_y"]))
    for namn, rader in per_serie.items():
        rader.sort()
        varden = [iy for _, iy in rader]
        assert varden == sorted(varden, reverse=True), f"{namn}: {rader}"


@pytest.mark.parametrize("liv", ["osb", "spanskiva"])
def test_axialkapacitet_ar_linjar_i_balkhojden(liv):
    """
    N_ck och N_tk vaxer linjart med h inom varje serie. Tabellen ar avrundad
    till 0.1 kN, sa avvikelsen fran den rata linjen far vara hogst det.
    """
    per_serie = {}
    for b in CFG["balk"][liv].values():
        per_serie.setdefault(b["serie"], []).append(
            (b["h"], b["N_ck"], b["N_tk"]))

    for serienamn, rader in per_serie.items():
        rader.sort()
        (h0, c0, t0), (h1, c1, t1) = rader[0], rader[-1]
        for h, c, t in rader:
            andel = (h - h0) / (h1 - h0)
            assert c == pytest.approx(c0 + (c1 - c0) * andel, abs=0.11), \
                f"{serienamn}{h} {liv}: N_ck"
            if t > 0 and t0 > 0:
                assert t == pytest.approx(t0 + (t1 - t0) * andel, abs=0.11), \
                    f"{serienamn}{h} {liv}: N_tk"


@pytest.mark.parametrize("liv,namn,b", ALLA, ids=[f"{n}" for _, n, _ in ALLA])
def test_dragkapacitet_i_forhallande_till_tryckkapacitet(liv, namn, b):
    """
    N_tk/N_ck ligger genomgaende pa 0.77-0.81 i bada ETA-tabellerna.
    Kvoten ar den kontroll som avslojade felet i tab. 11 for HB-serien:
    dar ger de tryckta N_tk-vardena kvoter kring 0.07-0.19.
    """
    if b["N_tk"] == -1:
        pytest.skip("N_tk saknas, se errata i balkar.toml")
    assert 0.77 <= b["N_tk"] / b["N_ck"] <= 0.81


def test_hb_med_osb_liv_har_ingen_dragkapacitet():
    """
    ETA tab. 11 upprepar M_k-kolumnen i N_tk-kolumnen for hela HB-serien.
    Vardena far INTE anvandas. Det har testet ser till att ingen fyller i
    dem utan att samtidigt ta bort errata-posten.

    Se [errata.eta_tab11_hb_ntk] i balkar.toml.
    """
    hb = {n: b for n, b in CFG["balk"]["osb"].items() if b["serie"] == "HB"}
    assert len(hb) == 9
    for namn, b in hb.items():
        assert b["N_tk"] == -1, (
            f"{namn}: N_tk ar ifylld. Ar vardet bekraftat av Masonite Beams "
            f"eller RISE? Ta i sa fall bort errata-posten samtidigt.")
        # Det tryckta felaktiga vardet var identiskt med M_k
        assert b["M_k"] != b["N_tk"]

    # Spanskivevarianten ar opaverkad och har rimliga varden
    for namn, b in CFG["balk"]["spanskiva"].items():
        if b["serie"] == "HB":
            assert b["N_tk"] > 150


@pytest.mark.parametrize("liv,namn,b", ALLA, ids=[f"{n}" for _, n, _ in ALLA])
def test_geometrin_gar_ihop(liv, namn, b):
    """Fri livhojd h - 2*h_flans maste vara positiv och jamn med h."""
    s = CFG["serie"][b["serie"]]
    h_liv = b["h"] - 2 * s["h_flans"]
    assert h_liv > 0
    assert h_liv == b["h"] - 94        # h_flans = 47 i alla fyra serier


def test_hojder_finns_i_upplagstabellerna():
    """
    Alla balkhojder i tab. 11/12 ska ga att slas upp i k_B-tabellen
    (tab. 8), som tacker 200-500. k_A (tab. 7) borjar forst vid 250.
    """
    hojder = {b["h"] for b in CFG["balk"]["osb"].values()}
    assert hojder <= set(CFG["upplag"]["k_B"]["h_rader"])
    assert hojder - set(CFG["upplag"]["k_A"]["h_rader"]) == {200, 220, 240}


def test_kmod_tvarkraft_ar_lagre_an_for_bojning():
    """
    ETA tab. 17: tvarkraft har egna, lagre k_mod som beror pa livmaterialet.
    Det ar latt att av vana anvanda bojningens k_mod overallt -- det har
    testet gor skillnaden explicit.
    """
    boj = CFG["kmod"]["bojning_upplag_axial"]
    tvar = CFG["kmod"]["tvarkraft"]
    for varaktighet in ("permanent", "lang", "medel", "kort"):
        for nyckel in ("osb_p7_kk1", "p5_kk1", "osb_p7_kk2", "p5_kk2"):
            kk = "kk1" if nyckel.endswith("kk1") else "kk2"
            assert tvar[nyckel][varaktighet] <= boj[kk][varaktighet]
    # P5 ar alltid samre an OSB/P7 i samma klimatklass
    for varaktighet in ("permanent", "lang", "medel", "kort", "momentan"):
        assert tvar["p5_kk1"][varaktighet] <= tvar["osb_p7_kk1"][varaktighet]
        assert tvar["p5_kk2"][varaktighet] <= tvar["osb_p7_kk2"][varaktighet]


def test_kdef_skjuvning_ar_storre_an_for_bojning():
    """
    ETA tab. 18: skjuvdeformationen kryper langt mer an bojdeformationen.
    Nedbojning i bruksgranstillstand maste darfor delas i tva delar med
    olika k_def.
    """
    boj = CFG["kdef"]["bojning_axial"]
    skjuv = CFG["kdef"]["skjuvning"]
    assert skjuv["osb_p7_kk1"] > boj["kk1"]
    assert skjuv["p5_kk1"] > skjuv["osb_p7_kk1"]
    assert skjuv["osb_p7_kk2"] > boj["kk2"]
    assert skjuv["p5_kk2"] > skjuv["osb_p7_kk2"]
