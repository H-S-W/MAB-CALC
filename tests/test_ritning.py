"""
Ritningarna ska ga att rita for varje konfiguration som berakningen
klarar -- de far aldrig bli det som falller appen.
"""

import tomllib
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

import berakning          # noqa: E402
import ritning            # noqa: E402

PROJEKTFIL = Path(__file__).parent.parent / "input" / "projekt.toml"


def cfg_med(**andringar):
    with open(PROJEKTFIL, "rb") as fh:
        c = tomllib.load(fh)
    for stig, varde in andringar.items():
        d = c
        *fore, sista = stig.split(".")
        for del_ in fore:
            d = d.setdefault(del_, {})
        d[sista] = varde
    return c


@pytest.mark.parametrize("andring", [
    {},
    {"system.nock_styv": False},
    {"geometri.balk": "HB500s"},
    {"forband.kolumner_flans": 2},
    {"laster.vind.q_p": 0.0, "plats.hamtat.v_b": 0.0},
])
def test_bada_ritningarna_gar_att_rita(andring):
    cfg = cfg_med(**andring)
    res = berakning.kor(cfg)
    f1 = ritning.takstol(cfg, res)
    f2 = ritning.nockforband(res, cfg)
    for f in (f1, f2):
        assert f.get_axes()
        f.canvas.draw()            # tvingar fram all text och alla matt


def test_spikarna_ritas_dar_berakningen_har_dem():
    """
    Figuren och I_p maste komma ur SAMMA koordinater. Ritningen vrider
    varje halva till sin sparre (lodrat stotfog i nocken), sa jamforelsen
    gors mot berakningens koordinater KORDA GENOM den vridningen.
    """
    from math import radians

    cfg = cfg_med()
    res = berakning.kor(cfg)
    alfa = radians(cfg["geometri"]["taklutning"])

    ritade = set()
    for samling in ritning.nockforband(res, cfg).get_axes()[0].collections:
        for px, py in samling.get_offsets():
            ritade.add((round(float(px), 3), round(float(py), 3)))

    vantade = set()
    for gr in res.grupper:
        for x, y in gr.grupp.coords:
            p = ritning._vrid(x, y, alfa, y > 0)
            vantade.add((round(float(p[0]), 3), round(float(p[1]), 3)))

    assert ritade == vantade


def test_vridningen_bevarar_avstanden():
    """
    Vridningen ar en ren rotation per halva: avstandet fran fogen till
    varje spik ska vara oforandrat, annars ritas en annan spikbild an den
    som raknats.
    """
    from math import hypot, radians

    alfa = radians(27.0)
    for x, y in ((0.0, 25.0), (100.0, -75.0), (-60.0, 40.0)):
        p = ritning._vrid(x, y, alfa, y > 0)
        assert hypot(*p) == pytest.approx(hypot(x, y))


def test_skivlangden_ar_spikbildens_utbredning_plus_kantavstand():
    cfg = cfg_med()
    res = berakning.kor(cfg)
    liv = next(g for g in res.grupper if "liv" in g.namn)
    y_max = max(abs(y) for _, y in liv.grupp.coords)
    # 15d = a3t: minst en skivande ar belastad i varje momentstyv
    # korning (spegelargumentet), och lyftfallet drar mot anden.
    # Granskningsfynd 2026-08-19, samma skarpning som stotfogens.
    vantat = 2 * (y_max + 15 * liv.forbindare.d)
    assert ritning._skivlangd(res, "liv", cfg["forband"]["cc_forbindare"])         == pytest.approx(vantat)
