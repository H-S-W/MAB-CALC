"""
Bjalklagskraven, handboken s. 229 korspravade mot Limtrahandbok del 2
tab. 6.1 s. 89. Raderna uteslots forst for att den tryckta tabellens
kolumner sag forskjutna ut; korsprovningen loste det.
"""

import pytest

import material


def test_bada_kalltabellerna_ger_samma_rader():
    """
    De fyra raderna med sina tolv varden. Stammer nagot inte mot
    handbokens s. 229 ELLER mot Limtrahandbokens tab. 6.1 ar avlasningen
    fel -- de tva ska vara identiska.
    """
    vantat = {
        "allmant": (500, 375, 300, None),
        "forrad": (275, 250, 200, None),
        "djurstall": (0, 200, 200, 30),
        "loge": (0, 150, 150, 40),
    }
    for nyckel, (inst, freq, fin, tak) in vantat.items():
        k = material.nedbojningskrav(nyckel, "bjalklag")
        assert k["u_inst"] == inst, nyckel
        assert k["u_freq"] == freq, nyckel
        assert k["u_fin"] == fin, nyckel
        assert k.get("u_fin_max_mm") == tak, nyckel


def test_bjalklag_ar_strangare_an_tak():
    """Ett golv far svikta mindre an ett tak -- L/500 mot L/375."""
    golv = material.nedbojningskrav("allmant", "bjalklag")
    tak = material.nedbojningskrav("allmant_utan_tak", "tak")
    assert golv["u_inst"] > tak["u_inst"]
    assert golv["u_fin"] == tak["u_fin"]


def test_takraven_ar_kvar_som_standard():
    """Befintliga anrop utan del_ ska fortsatta traffa takraderna."""
    assert material.nedbojningskrav("allmant_utan_tak") ==         material.nedbojningskrav("allmant_utan_tak", "tak")


def test_okand_del_och_nyckel_sager_ifran():
    with pytest.raises(KeyError, match="tak"):
        material.nedbojningskrav("allmant", "vagg")
    with pytest.raises(KeyError, match="finns inte"):
        material.nedbojningskrav("finns_inte", "bjalklag")


def test_namnlistan_ar_sorterad_och_komplett():
    assert material.nedbojningskravnamn("bjalklag") ==         ["allmant", "djurstall", "forrad", "loge"]
    assert "allmant_utan_tak" in material.nedbojningskravnamn("tak")
