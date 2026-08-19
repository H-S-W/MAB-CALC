"""
SS-EN 338:2016 tab. 1 och kopplingen till knackningen.

ETA 12/0018 avsn. 1.2.4 ar entydig: axialkraftskapaciteten raknas enligt
EC5 med hallfasthets- och STYVHETSVARDEN ur EN 338, och C30+ raknas som
C30. Knackningens E_0,05 ska darfor vara 8 000 MPa, inte 0,67 x ETA:ns
forhojda C30+-medelvarde 13 000 = 8 710.
"""

import tomllib
from pathlib import Path

import pytest

import berakning
import material

PROJEKTFIL = Path(__file__).parent.parent / "input" / "projekt.toml"


def grund():
    with open(PROJEKTFIL, "rb") as fh:
        return tomllib.load(fh)


def test_en338_tabellen_ar_komplett():
    """Alla tre klasserna med alla nio storheterna."""
    for klass in ("C18", "C24", "C30"):
        rad = material.en338(klass)
        for nyckel in ("f_m_k", "f_t_0_k", "f_c_0_k", "f_v_k", "E_0_mean",
                       "E_0_05", "G_mean", "rho_k", "rho_mean"):
            assert rad[nyckel] > 0, (klass, nyckel)


def test_en384_harledningarna_stammer():
    """
    EN 384: E_0,05 = 0,67*E_0,mean och G_mean = E_0,mean/16 for barrtra.
    Stammer de inom 1 % ar avlasningen av E-modulerna med sakerhet ratt.
    """
    for klass in ("C18", "C24", "C30"):
        r = material.en338(klass)
        assert r["E_0_05"] == pytest.approx(0.67 * r["E_0_mean"], rel=0.01)
        assert r["G_mean"] == pytest.approx(r["E_0_mean"] / 16, rel=0.01)


def test_skjuvhallfastheten_ar_kapad_vid_4_0():
    """
    C30 har SAMMA f_v_k som C24 (4,0 MPa) i 2016 ars utgava. Det ser ut
    som ett tryckfel men ar riktigt -- rakna inte upp det.
    """
    assert material.en338("C30")["f_v_k"] == \
        material.en338("C24")["f_v_k"] == 4.0
    assert material.en338("C18")["f_v_k"] == 3.4


def test_utgavan_ar_2016_inte_utkastet():
    """
    Utkastet prEN 338:2013 cirkulerar under filnamn som ser ut som
    2016-utgavan. Skillnaden syns pa dragvardena: utkastet har
    f_t_0_k = 14,0 for C24, utgavan 14,5.
    """
    assert material.en338("C24")["f_t_0_k"] == 14.5
    assert material.en338("C30")["f_c_0_k"] == 24.0


def test_densiteterna_stammer_med_flansdatat():
    """[flans.*] bar redan EN 338:s densiteter -- de maste vara samma."""
    for kval, data in material.flanskvaliteter().items():
        if "en338" not in data:
            continue
        rad = material.en338(data["en338"])
        assert data["rho_k"] == rad["rho_k"], kval
        assert data["rho_mean"] == rad["rho_mean"], kval


def test_e05_kvoten_harleds_ur_en338():
    """8 000 / 13 000 for C30+, inte 0,67."""
    assert material.e05_kvot("C30plus") == pytest.approx(8000 / 13000)
    assert material.e05_kvot("C24plus") == pytest.approx(7400 / 11000)
    assert material.e05_kvot("C18") == pytest.approx(6000 / 9000)
    # den gamla schablonen var 8,9 % for hog for C30+
    assert 0.67 / material.e05_kvot("C30plus") == pytest.approx(1.089,
                                                                abs=0.002)


def test_kedjan_anvander_den_harledda_kvoten():
    res = berakning.kor(grund())
    assert res.antaganden
    rad = next(a for a in res.antaganden if a.startswith("EI_05"))
    assert "HÄRLETT" in rad and "1.2.4" in rad and "8000" in rad
    assert "0.6154" in rad


def test_overstyrning_respekteras_och_flaggas():
    cfg = grund()
    cfg["dimensionering"]["E05_kvot"] = 0.67
    res = berakning.kor(cfg)
    rad = next(a for a in res.antaganden if a.startswith("EI_05"))
    assert "ÖVERSTYRD" in rad
    # och den ger ett LAGRE utnyttjande -- det var det som var felet
    assert (res.varsta_balkkontroll.utnyttjande
            < berakning.kor(grund()).varsta_balkkontroll.utnyttjande)
