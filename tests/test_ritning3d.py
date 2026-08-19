"""
3D-modellen ska vara byggd ur SAMMA koordinater som berakningen --
spiklagen ar vrid_till_nock av exakt de coords som I_p raknas med, och
produktionstabellen ar samma data. Har lases den kopplingen, plus att
spikarnas djup ar fysikaliskt riktiga (livspik gar genom livet,
flansspik stannar i flansen).
"""

from math import radians

import pytest
import tomllib
from pathlib import Path

import berakning
import ritning3d
from forband import vrid_till_nock

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


@pytest.fixture(scope="module")
def res():
    cfg = cfg_med()
    return berakning.kor(cfg), cfg


def test_spiklagen_ar_berakningens_koordinater(res):
    """Bild = siffra: varje spik i 3D ligger dar berakningen raknar den."""
    r, cfg = res
    geo = ritning3d.geometri(r, cfg, detalj=True)
    alfa = radians(cfg["geometri"]["taklutning"])
    # OBS: samma avrundning som tabellen (round(v, 1) direkt) --
    # dubbelavrundning via 3 decimaler ger andra varden vid ,x5-granser.
    vantade = set()
    for gr in r.grupper:
        for x, y in set(gr.grupp.coords):
            px, pz = vrid_till_nock(x, y, alfa)
            vantade.add((round(px, 1), round(pz, 1)))
    fanns = {(rad["x_mm"], rad["z_mm"]) for rad in geo["spiktabell"]}
    assert fanns == vantade


def test_antalet_stammer_med_grupperna(res):
    """Tabellens rader = summan av gr.antal (en spikbild per sida)."""
    r, cfg = res
    geo = ritning3d.geometri(r, cfg, detalj=True)
    assert len(geo["spiktabell"]) == sum(gr.antal for gr in r.grupper)
    for grupp in geo["spikgrupper"]:
        gr = next(g for g in r.grupper if g.namn == grupp["namn"])
        assert len(grupp["segment"]) == gr.antal


def test_spikdjupen_ar_fysikaliska(res):
    """
    Livspiken (genom skiva -> LIV -> skiva) ska korsa balkens mittplan;
    flansspiken (ett snitt) ska borja utanfor flansen och sluta INNE i
    flansbredden. Bada slas fran bada sidor.
    """
    r, cfg = res
    geo = ritning3d.geometri(r, cfg, detalj=True)
    bf, tl = r.balk.b_flans, r.balk.t_liv
    t = cfg["forband"]["skiva_t"]
    for grupp in geo["spikgrupper"]:
        i_flans = "flans" in grupp["namn"]
        sidor = set()
        for (a, b) in grupp["segment"]:
            y0, y1 = a[1], b[1]
            sidor.add(1 if y0 > 0 else -1)
            if i_flans:
                assert abs(y0) == pytest.approx(bf / 2 + t)
                assert abs(y1) < bf / 2          # spetsen inne i flansen
            else:
                assert abs(y0) == pytest.approx(tl / 2 + t)
                assert y0 * y1 < 0               # genom mittplanet
        assert sidor == {1, -1}


def test_skivorna_omsluter_sina_spikar(res):
    """Varje spik ligger inom sin skivas bbox i elevationen."""
    r, cfg = res
    geo = ritning3d.geometri(r, cfg, detalj=True)
    for sk in geo["skivor"]:
        xs = [p[0] for p in sk["horn"]]
        zs = [p[1] for p in sk["horn"]]
        rader = [rad for rad in geo["spiktabell"]
                 if rad["skiva"] == sk["namn"]]
        assert rader
        for rad in rader:
            assert min(xs) - 1e-6 <= rad["x_mm"] <= max(xs) + 1e-6
            assert min(zs) - 1e-6 <= rad["z_mm"] <= max(zs) + 1e-6


def test_ledad_nock_har_bara_livskivor():
    cfg = cfg_med(**{"system.nock_styv": False})
    r = berakning.kor(cfg)
    geo = ritning3d.geometri(r, cfg, detalj=True)
    assert [sk["namn"] for sk in geo["skivor"]] == ["Livforstarkning"]
    assert len(geo["spiktabell"]) == 2 * r.ledad.grupp.n
    assert all(rad["skiva"] == "Livforstarkning"
               for rad in geo["spiktabell"])


def test_hela_takstolen_har_upplag_och_spannvidd():
    from math import cos, tan
    cfg = cfg_med()
    r = berakning.kor(cfg)
    geo = ritning3d.geometri(r, cfg, detalj=False)
    namn = [pr["namn"] for pr in geo["prismor"]]
    assert "Upplag (vänster)" in namn and "Upplag (höger)" in namn
    L = cfg["geometri"]["spannvidd"] * 1000.0
    spann = next(m for m in geo["matt"] if "spännvidd" in m["text"])
    assert abs(spann["b"][0] - spann["a"][0]) == pytest.approx(L)

    # ANLIGGNINGEN (granskningsfynd 2026-08-19): upplagets overyta ska
    # folja balkens underkant z(x) = -x*tan(alfa) - (h/2)/cos(alfa),
    # och balken ska tacka hela kontaktstrackan.
    alfa = radians(cfg["geometri"]["taklutning"])
    h = r.balk.h

    def underkant(x):
        return -x * tan(alfa) - (h / 2) / cos(alfa)

    stod = next(p for p in geo["prismor"] if p["namn"] == "Upplag (höger)")
    topphorn = sorted(stod["poly"], key=lambda p: -p[1])[:2]
    for x, z in topphorn:
        assert z == pytest.approx(underkant(x), abs=1e-6)
    x_stod_max = max(p[0] for p in stod["poly"])
    flans = next(p for p in geo["prismor"]
                 if p["namn"] == "Underfläns (höger)")
    assert max(p[0] for p in flans["poly"]) >= x_stod_max - 1e-6

    # utsticket matt fran stodets YTTERKANT, inte centrumlinjen
    cfg2 = cfg_med(**{"upplag.overhang_y": 150.0})
    r2 = berakning.kor(cfg2)
    geo2 = ritning3d.geometri(r2, cfg2, detalj=False)
    ut = next(m for m in geo2["matt"] if "utstick" in m["text"])
    assert "ytterkant" in ut["text"]
    dx = ut["b"][0] - ut["a"][0]
    dz = ut["b"][2] - ut["a"][2]
    assert (dx * dx + dz * dz) ** 0.5 == pytest.approx(150.0)


@pytest.mark.parametrize("andring", [
    {},
    {"system.nock_styv": False},
    {"forband.spikmonster": "rutnat"},
    {"forband.kolumner_flans": 2},
    {"geometri.balk": "HB500s"},
])
def test_modellen_gar_att_bygga(andring):
    """3D-modellen far aldrig vara det som faller appen."""
    pytest.importorskip("plotly")      # geometri()-testerna klarar sig utan
    cfg = cfg_med(**andring)
    r = berakning.kor(cfg)
    for detalj in (True, False):
        fig = ritning3d.modell(r, cfg, detalj=detalj)
        assert len(fig.data) > 0


def test_trianguleringen_klarar_skivans_konkava_kontur():
    """Skivkonturen ar konkav i underkant; n horn ska ge n-2 trianglar
    som alla har positiv area (moturs)."""
    from ritning import _skivhorn
    poly = [(float(p[0]), float(p[1]))
            for p in _skivhorn(radians(27), 300.0, 400.0)]
    tri = ritning3d._triangulering(poly)
    assert len(tri) == len(poly) - 2
    for a, b, c in tri:
        assert ritning3d._kryss(poly[a], poly[b], poly[c]) > 0
