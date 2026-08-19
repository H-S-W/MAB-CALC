"""
Verifiering av src/forbindare_ec5.py mot EN 1995-1-1 kap. 8 och mot
handbokens egna antagna spikkapaciteter.

Den starkaste kontrollen ar handboken sjalv: den anger 0,36 kN/snitt for
spik i flansen och 0,30 kN/snitt for spik i livforstarkningen, for en
2,5x50 spik med k_mod = 0,8. Raknar man fram samma sak ur EC5 8.2.2 ska
man landa pa samma storleksordning. Gor man inte det ar antingen formlerna
fel implementerade eller handbokens varden hamtade nagon annanstans.
"""

import tomllib
from pathlib import Path

import pytest

from forbindare_ec5 import (
    Forbindare, M_y_Rk, dubbelsnitt, enkelsnitt, f_h_osb_spanskiva,
    f_h_plywood, f_h_tra, kontrollera_intrangning, minsta_avstand,
    minsta_intrangning, minsta_tjocklek_mot_sprickning, repeffekt_andel)

MATERIAL = Path(__file__).parent.parent / "input" / "material"
BALKAR = tomllib.load(open(MATERIAL / "balkar.toml", "rb"))
SKIVOR = tomllib.load(open(MATERIAL / "skivor.toml", "rb"))
FORBINDARE = tomllib.load(open(MATERIAL / "forbindare.toml", "rb"))

# Handbokens forutsattningar i exempel 5.3.4.1
RHO_FLANS = BALKAR["flans"]["C30plus"]["rho_k"]          # 380, EN 338 C30
RHO_PLYWOOD = SKIVOR["skiva"]["plywood_handbok"]["hallfasthet"]["rho_k"]
K_MOD = SKIVOR["kmod"]["plywood_handbok"]["kk1"]["medel"]   # 0.80
GAMMA_M = FORBINDARE["metadata"]["gamma_M_forband"]         # 1.30
T_PLYWOOD = 18.0
T_LIV = 10.0

SLAT = Forbindare("Tradspik 2.5x50", d=2.5, langd=50.0, typ="rund")
RILLAD = Forbindare("Ankarspik 2.5x50", d=2.5, langd=50.0, typ="rillad")


def flansgruppen(f):
    """Utanpaliggande skiva mot flans: enkelsnitt, plywood in i tra."""
    return enkelsnitt(f, f_h_plywood(RHO_PLYWOOD, f.d), T_PLYWOOD,
                      f_h_tra(RHO_FLANS, f.d, f.forborrning),
                      f.langd - T_PLYWOOD)


def livgruppen(f, t_liv=T_LIV):
    """Livforstarkning: dubbelsnitt, plywood - liv - plywood."""
    return dubbelsnitt(f, f_h_plywood(RHO_PLYWOOD, f.d), T_PLYWOOD,
                       f_h_osb_spanskiva(f.d, t_liv), t_liv)


# ---------------------------------------------------------------------------
# Halkantshallfasthet
# ---------------------------------------------------------------------------

def test_f_h_plywood_ekv_8_20():
    """f_h,k = 0,11 * rho_k * d^-0,3. rho_k = 410, d = 2,5 ger 34,3 MPa."""
    assert f_h_plywood(410, 2.5) == pytest.approx(34.27, abs=0.02)


def test_f_h_tra_ekv_8_15():
    """f_h,k = 0,082 * rho_k * d^-0,3. rho_k = 380, d = 2,5 ger 23,7 MPa."""
    assert f_h_tra(380, 2.5) == pytest.approx(23.67, abs=0.02)


def test_f_h_plywood_ar_starkare_an_tra_med_samma_densitet():
    """Koefficienten ar 0,11 mot 0,082, alltsa 34 % hogre."""
    assert f_h_plywood(400, 3.0) / f_h_tra(400, 3.0) == \
        pytest.approx(0.11 / 0.082, rel=1e-9)


def test_f_h_osb_ekv_8_22_beror_pa_tjocklek_inte_densitet():
    """
    f_h,k = 65 * d^-0,7 * t^0,1. Formeln har ingen densitet, till skillnad
    fran tra och plywood. En tjockare skiva ger hogre varde.
    """
    assert f_h_osb_spanskiva(2.5, 10.0) == pytest.approx(43.10, abs=0.02)
    assert f_h_osb_spanskiva(2.5, 20.0) > f_h_osb_spanskiva(2.5, 10.0)


def test_forborrning_andrar_f_h_i_tra():
    """Ekv. 8.16 galler vid forborrning och ger ett annat varde an 8.15."""
    assert f_h_tra(380, 2.5, forborrning=True) != f_h_tra(380, 2.5)


# ---------------------------------------------------------------------------
# Flytmoment
# ---------------------------------------------------------------------------

def test_M_y_Rk_ekv_8_14():
    """0,3 * f_u * d^2,6 for rund spik: 0,3 * 600 * 2,5^2,6 = 1949 Nmm."""
    assert M_y_Rk(SLAT) == pytest.approx(1949, abs=2)


def test_rillad_spik_har_1_5_ganger_flytmomentet():
    """Koefficienten ar 0,45 mot 0,30."""
    assert M_y_Rk(RILLAD) / M_y_Rk(SLAT) == pytest.approx(0.45 / 0.30)


# ---------------------------------------------------------------------------
# Jamforelse med handbokens antagna varden
# ---------------------------------------------------------------------------

def test_flansgruppen_reproducerar_handbokens_0_36_kN():
    """
    Handboken s. 288: F_nail.flange = 0,36 kN/snitt vid k_mod = 0,8.

    EC5 8.2.2 med slat spik ger 0,370 kN, dvs 3 % over handbokens varde.
    Det ar sa nara man kan komma utan att veta exakt vilken spik och
    vilket f_u handboken har utgatt fran, och bekraftar att brottmoderna
    ar rätt implementerade.
    """
    F_Rd = flansgruppen(SLAT).F_v_Rd_kN(K_MOD, GAMMA_M)
    assert F_Rd == pytest.approx(0.36, rel=0.05)


def test_livgruppen_reproducerar_handbokens_0_30_kN():
    """
    Handboken s. 289: F_nail.web = 0,30 kN/snitt vid k_mod = 0,8.

    EC5 8.7 ger 0,331 kN per skjuvsnitt, dvs 10 % over. Skillnaden ar
    rimlig givet att 0,30 ar ett avrundat tal.
    """
    F_Rd = livgruppen(SLAT).F_v_Rd_kN(K_MOD, GAMMA_M)
    assert F_Rd == pytest.approx(0.30, rel=0.12)


def test_flansgruppens_kapacitet_ar_last():
    """
    Regressionslas. Andras nagon formel ska det synas som ett trasigt test
    och inte som ett tyst andrat dimensioneringsresultat.
    """
    slat, rillad = flansgruppen(SLAT), flansgruppen(RILLAD)
    assert slat.F_v_Rk_kN == pytest.approx(0.601, abs=0.001)
    assert slat.brottmod == "8.6f"
    assert rillad.F_v_Rk_kN == pytest.approx(0.647, abs=0.001)
    assert rillad.brottmod == "8.6d"


def test_livgruppens_kapacitet_ar_last():
    """
    Dubbelsnittet styrs av mellandelens halkantsbrott, ekv. 8.7h, som ar
    0,5 * f_h,2 * t_2 * d. Det ar 10 mm-livet som ar den svaga lanken --
    darfor blir kapaciteten densamma for slat och rillad spik, eftersom
    8.7h inte innehaller flytmomentet.
    """
    slat, rillad = livgruppen(SLAT), livgruppen(RILLAD)
    assert slat.F_v_Rk_kN == pytest.approx(0.539, abs=0.001)
    assert slat.brottmod == "8.7h"
    assert rillad.F_v_Rk_kN == pytest.approx(slat.F_v_Rk_kN, abs=1e-9)
    assert rillad.brottmod == "8.7h"


def test_rillad_spik_hjalper_i_flansen_men_inte_i_livet():
    """
    En konsekvens som ar vard att se: att byta till ringad spik hojer
    flansgruppen 8 % men gor ingenting for livgruppen, eftersom den styrs
    av en mod utan flytmoment. Att lagga pengar pa grovre spik i livet ar
    darfor bortkastat sa lange livet ar 10 mm.
    """
    assert flansgruppen(RILLAD).F_v_Rk_kN > flansgruppen(SLAT).F_v_Rk_kN
    assert livgruppen(RILLAD).F_v_Rk_kN == \
        pytest.approx(livgruppen(SLAT).F_v_Rk_kN)


# ---------------------------------------------------------------------------
# ERRATA punkt 2: far tva skjuvsnitt raknas i livforstarkningen?
# ---------------------------------------------------------------------------

def test_intrangningen_racker_for_bortre_skjuvsnittet():
    """
    docs/ERRATA.md punkt 2 lamnar fragan oppen: tva skjuvsnitt far anvandas
    om 8.3.1.1:s inträngningskrav ar uppfyllt. Nu gar det att rakna.

    En 2,5x50 spik genom 18 + 10 + 18 mm har 22 mm kvar i sista delen.
    Kravet ar 8d = 20 mm for slat spik och 6d = 15 mm for rillad. Bada
    uppfylls, alltsa far det bortre skjuvsnittet raknas.
    """
    for f in (SLAT, RILLAD):
        res = kontrollera_intrangning(f, [T_PLYWOOD, T_LIV, T_PLYWOOD])
        assert res.intrangning == pytest.approx(22.0)
        assert res.uppfyllt, res.fel
        assert res.fel == []
    assert minsta_intrangning(SLAT) == 20.0
    assert minsta_intrangning(RILLAD) == 15.0


def test_spetsen_sticker_ut_men_det_ar_ingen_kapacitetsfraga():
    """22 mm inträngning i en 18 mm skiva ger 4 mm utstickande spets."""
    res = kontrollera_intrangning(SLAT, [T_PLYWOOD, T_LIV, T_PLYWOOD])
    assert res.uppfyllt
    assert len(res.anmarkningar) == 1
    assert "4.0 mm ut" in res.anmarkningar[0]


def test_for_kort_spik_forbjuder_det_bortre_skjuvsnittet():
    """En 2,5x40 spik har bara 12 mm kvar, under bade 8d och 6d."""
    kort = Forbindare("Spik 2.5x40", d=2.5, langd=40.0, typ="rund")
    res = kontrollera_intrangning(kort, [T_PLYWOOD, T_LIV, T_PLYWOOD])
    assert not res.uppfyllt
    assert "far inte raknas" in res.fel[0]


def test_spik_som_inte_naar_fram_till_sista_delen():
    kortare = Forbindare("Spik 2.5x25", d=2.5, langd=25.0, typ="rund")
    res = kontrollera_intrangning(kortare, [T_PLYWOOD, T_LIV, T_PLYWOOD])
    assert not res.uppfyllt
    assert "naar inte ens fram" in res.fel[0]


def test_dubbelsnitt_ger_inte_dubbla_kapaciteten_per_snitt():
    """
    Viktig nyans. Att tva skjuvsnitt far raknas betyder inte att varje snitt
    ar lika starkt som i ett enkelsnittsforband -- men har rakar de vara
    nastan lika: 0,539 mot 0,533 kN per snitt. Per SPIK blir dubbelsnittet
    darfor narmast dubbelt sa starkt.
    """
    per_snitt_dubbel = livgruppen(SLAT).F_v_Rk_kN
    per_snitt_enkel = enkelsnitt(
        SLAT, f_h_plywood(RHO_PLYWOOD, 2.5), T_PLYWOOD,
        f_h_osb_spanskiva(2.5, T_LIV), T_LIV).F_v_Rk_kN
    assert per_snitt_dubbel == pytest.approx(per_snitt_enkel, rel=0.05)


# ---------------------------------------------------------------------------
# Repeffekt
# ---------------------------------------------------------------------------

def test_ingen_repeffekt_som_default():
    """F_ax_Rk = 0 ger inget tillskott. Handboken raknar inte med repeffekt."""
    assert flansgruppen(SLAT).repeffekt_kN == 0.0


def test_repeffekten_kapas_mot_tabell_8_1():
    """
    Tab. 8.1: repeffekten far vara hogst 15 % av Johansendelen for runda
    spikar och 25 % for rillade. Ett orimligt stort F_ax_Rk ska darfor inte
    ge mer an den andelen.
    """
    assert repeffekt_andel("rund") == 0.15
    assert repeffekt_andel("rillad") == 0.25

    utan = flansgruppen(SLAT).F_v_Rk_kN
    med = flansgruppen(Forbindare("test", d=2.5, langd=50.0, typ="rund",
                                  F_ax_Rk=100_000)).F_v_Rk_kN
    assert med / utan == pytest.approx(1.15, rel=0.001)


def test_repeffekten_hojer_bara_flytmoderna():
    """
    Repeffekten galler moderna dar forbindaren flyter. Livgruppen styrs av
    8.7h, en ren halkantsmod, och ska darfor inte paverkas alls.
    """
    med = livgruppen(Forbindare("test", d=2.5, langd=50.0, typ="rund",
                                F_ax_Rk=100_000))
    assert med.brottmod == "8.7h"
    assert med.repeffekt_kN == 0.0


# ---------------------------------------------------------------------------
# Avstand och sprickning
# ---------------------------------------------------------------------------

def test_avstanden_ger_handbokens_25_mm_rutnat():
    """
    Tab. 8.2 for spik utan forborrning, d < 5 mm, rho_k <= 420:
    a1 = (5 + 5|cos alpha|)d och a2 = 5d. Vid alpha = 0 och d = 2,5 blir
    det 25,0 och 12,5 mm, vilket ar precis handbokens rutnat.
    """
    a = minsta_avstand(SLAT, alpha=0.0, rho_k=RHO_FLANS)
    assert a["a1"] == 25.0
    assert a["a2"] == 12.5
    assert a["a3c"] == 25.0


def test_avstandet_langs_fibrerna_minskar_med_vinkeln():
    """Vid alpha = 90 grader ar cos = 0, sa a1 gar fran 10d till 5d."""
    assert minsta_avstand(SLAT, alpha=90.0)["a1"] == pytest.approx(12.5)


def test_grovre_spik_kraver_storre_avstand():
    """a1 ar proportionell mot d, sa en 3,1 mm spik kraver 31 mm."""
    grov = Forbindare("Spik 3.1x75", d=3.1, langd=75.0, typ="rillad")
    assert minsta_avstand(grov)["a1"] == pytest.approx(31.0)


def test_flansen_ar_tjock_nog_for_spikning_utan_forborrning():
    """
    8.3.1.2: t = max(7d ; (13d-30) * rho_k/400). For d = 2,5 ger det
    17,5 mm, vilket flansens 47 mm klarar med marginal.
    """
    krav = minsta_tjocklek_mot_sprickning(SLAT, RHO_FLANS)
    assert krav == pytest.approx(17.5)
    assert krav < 47.0


def test_sprickkravet_styrs_av_andra_termen_for_grov_spik():
    """For d = 4,0 mm och rho_k = 380 blir (13d-30)*rho_k/400 = 20,9 mm."""
    grov = Forbindare("Spik 4.0x100", d=4.0, langd=100.0, typ="rund")
    assert minsta_tjocklek_mot_sprickning(grov, 380) == \
        pytest.approx(max(28.0, 20.9), abs=0.05)


# ---------------------------------------------------------------------------
# Biblioteket
# ---------------------------------------------------------------------------

def test_alla_forbindare_i_biblioteket_gar_att_rakna_pa():
    """
    Varje post ska ge en positiv kapacitet i bade flans och liv, och ha en
    giltig typ. Fangar en felstavad typ eller ett glomt falt.
    """
    for nyckel, rad in FORBINDARE["forbindare"].items():
        f = Forbindare(namn=rad["namn"], d=rad["d"], langd=rad["langd"],
                       f_u=rad["f_u"], typ=rad["typ"],
                       forborrning=rad["forborrning"],
                       F_ax_Rk=rad["F_ax_Rk"])
        assert flansgruppen(f).F_v_Rk_kN > 0, nyckel
        assert livgruppen(f).F_v_Rk_kN > 0, nyckel
        assert minsta_avstand(f)["a1"] == pytest.approx(10 * f.d)


def test_handbokens_referensspik_finns_i_biblioteket():
    assert "ankarspik_2_5x50" in FORBINDARE["forbindare"]
    rad = FORBINDARE["forbindare"]["ankarspik_2_5x50"]
    assert (rad["d"], rad["langd"]) == (2.5, 50.0)


def test_gamma_M_for_forband_ar_1_30():
    """EN 1995-1-1 tab. 2.3: gamma_M = 1,3 for forband."""
    assert GAMMA_M == 1.30


# ---------------------------------------------------------------------------
# Ogiltiga anrop ska faila, inte tyst ge fel svar
# ---------------------------------------------------------------------------

def test_okand_forbindartyp_avvisas():
    with pytest.raises(ValueError):
        Forbindare("fel", d=2.5, langd=50.0, typ="spiralformad")


def test_avstandstabellen_avvisar_fall_den_inte_tacker():
    """
    Tab. 8.2 har flera rader. Modulen implementerar bara raden for spik
    utan forborrning med d < 5 mm i tra med rho_k <= 420. Ovriga fall ska
    hoja fel i stallet for att ge varden fran fel rad.
    """
    grov = Forbindare("Skruv 6x80", d=6.0, langd=80.0, typ="rund")
    with pytest.raises(NotImplementedError):
        minsta_avstand(grov)

    with pytest.raises(NotImplementedError):
        minsta_avstand(SLAT, rho_k=500)

    forborrad = Forbindare("Spik 2.5x50 fb", d=2.5, langd=50.0,
                           typ="rund", forborrning=True)
    with pytest.raises(NotImplementedError):
        minsta_avstand(forborrad)
