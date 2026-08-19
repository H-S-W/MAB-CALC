"""
Verifiering av ram.takstol_b1 mot jamvikt, symmetri och gransfall.

Modellen (handboken s. 283 + 5.3.5-5.3.7): stodben momentstyva, hanbjalke
ledad i bada andar, nock ledad, underramen ar dragband mellan upplagen.
"""

import numpy as np
import pytest

import berakning
from ram import takstol_b1

EA, EI, GA = 350000.0, 4000.0, 5000.0
L, ALPHA, H_STOD, H_HB = 10.0, 40.0, 1.2, 1.5
W = 2.0                       # kN/m horisontalprojektion


def b1(w_tak=W, w_golv=0.0, h_hb=H_HB, **kw):
    fr, ix = takstol_b1(L, ALPHA, H_STOD, EA, EI, GA=None,
                        h_hanbjalke=h_hb, **kw)
    for e in ix["vanster"] + ix["hoger"]:
        fr.set_udl_projected(e, -w_tak)
    for e in ix["underram"]:
        fr.set_udl(e, -w_golv)
    fr.solve()
    return fr, ix


def test_jamvikt():
    fr, ix = b1(w_tak=W, w_golv=1.5)
    Ry = sum(fr.reactions[3 * n + 1] for n in (ix["left"], ix["right"]))
    assert Ry == pytest.approx(W * L + 1.5 * L, rel=1e-9)
    Rx = sum(fr.reactions[3 * n + 0] for n in (ix["left"], ix["right"]))
    assert Rx == pytest.approx(0.0, abs=1e-9)


def test_symmetri():
    """
    Reaktioner och lodrata nedbojningar speglar varandra. I SIDLED driver
    hela ramen at hoger: hoger upplag ar rullager, sa underramens
    forlangning gar dit -- nocken foljer med halva vagen. Det ar
    stelkroppsforskjutningen, inte en asymmetri.
    """
    fr, ix = b1()
    assert fr.reactions[3 * ix["left"] + 1] == \
        pytest.approx(fr.reactions[3 * ix["right"] + 1], rel=1e-9)
    uv = [fr.node_disp(n)[1] for n in ix["vanster_noder"]]
    uh = [fr.node_disp(n)[1] for n in ix["hoger_noder"]]
    assert uv == pytest.approx(uh, rel=1e-6)
    ux_B = fr.node_disp(ix["right"])[0]
    assert ux_B > 0
    assert fr.node_disp(ix["apex"])[0] == pytest.approx(ux_B / 2, rel=1e-9)
    assert fr.node_disp(ix["left"])[0] == pytest.approx(0.0, abs=1e-15)


def test_geometrin_byggs_dar_den_ska():
    """
    Nodplaceringen ar det som latt blir fel i en byggare: takfoten ligger
    h_stod over upplaget, nocken h_stod + L/2*tan(alpha), och hanbjalken
    dar sparren nar sin hojd, x = h_hb/tan(alpha).
    """
    fr, ix = takstol_b1(L, ALPHA, H_STOD, EA, EI, h_hanbjalke=H_HB)
    rise = L / 2 * np.tan(np.radians(ALPHA))
    assert fr.nodes[ix["left"]] == pytest.approx((0.0, 0.0))
    assert fr.nodes[ix["right"]] == pytest.approx((L, 0.0))
    assert fr.nodes[ix["takfot_v"]] == pytest.approx((0.0, H_STOD))
    assert fr.nodes[ix["apex"]] == pytest.approx((L / 2, H_STOD + rise))
    x_hb = H_HB / np.tan(np.radians(ALPHA))
    assert ix["x_hb"] == pytest.approx(x_hb)
    assert fr.nodes[ix["han_v"]] == pytest.approx((x_hb, H_STOD + H_HB))
    assert fr.nodes[ix["han_h"]] == pytest.approx((L - x_hb, H_STOD + H_HB))
    # hanbjalkens noder ligger PA sparrarna
    for n in (ix["han_v"], ix["han_h"]):
        x, y = fr.nodes[n]
        assert y == pytest.approx(H_STOD + min(x, L - x)
                                  * np.tan(np.radians(ALPHA)))


def test_nocken_ar_ledad():
    """5.3.7 galler a1, b1 och c1: nocken overfor N och V, inte moment."""
    fr, ix = b1()
    assert fr.internal(ix["vanster"][-1])[3][-1] == pytest.approx(0, abs=1e-9)
    assert fr.internal(ix["hoger"][0])[3][0] == pytest.approx(0, abs=1e-9)


def kordaavvikelse(fr, noder):
    """
    Sparrens utbojning vinkelratt kordan [mm]. Anvander PRODUKTIONENS
    egen funktion, sa att b1 provar exakt det matt nedbojnings-
    kontrollen anvander -- inklusive att kordan parametriseras pa
    nodernas LAGE. Elementen ar olika langa nar hanbjalken delar
    sparren, och en indexparametrisering ger da upp till 14 % fel.
    """
    return float(np.max(np.abs(
        berakning._avvikelse_fran_korda(fr, noder)))) * 1000


def faltmoment(fr, kedja):
    """
    Faltmomentet [kNm] = storsta POSITIVA (dragning i underkant)
    momentet langs sparren. Teckenet skiljer det fran knamomentet vid
    takfoten, som ar negativt -- ett max|M| over kedja[1:] far i stallet
    med det som lacker in i element 1 och blir darmed natberoende.
    """
    return max(fr.internal(e)[3].max() for e in kedja)


def test_hanbjalken_avlastar_sparren():
    """
    Hanbjalken halver sparrens utbojning och sanker faltmomentet -- ju
    hogre upp desto mer. Den ar TRYCKT: sparrarna bojer sig inat mot
    varandra och hanbjalken haller emot.
    """
    matt = {}
    for h_hb in (None, 1.5, 3.0):
        fr, ix = b1(h_hb=h_hb)
        matt[h_hb] = (kordaavvikelse(fr, ix["vanster_noder"]),
                      faltmoment(fr, ix["vanster"]))
    assert matt[1.5][0] < 0.6 * matt[None][0]      # 1,88 mot 3,34 mm
    assert matt[3.0][0] < 0.25 * matt[None][0]     # 0,68 mm
    assert matt[1.5][1] < matt[None][1]            # 2,79 mot 3,84 kNm
    assert matt[3.0][1] < matt[1.5][1]             # 1,31 kNm


def test_matten_ar_natoberoende():
    """
    Bade kordaavvikelsen och faltmomentet ska ge samma svar oavsett hur
    fint sparren delas. Regressionstest for tva fel som doldes av
    varandra: kordan parametriserad pa nodindex, och ett "faltmoment"
    som i sjalva verket var max|M| och darmed fangade knamomentet.
    """
    varden = {}
    for ne in (8, 16, 40):
        fr, ix = takstol_b1(L, ALPHA, H_STOD, EA, EI, h_hanbjalke=H_HB,
                            n_elem=ne)
        for e in ix["vanster"] + ix["hoger"]:
            fr.set_udl_projected(e, -W)
        fr.solve()
        varden[ne] = (kordaavvikelse(fr, ix["vanster_noder"]),
                      faltmoment(fr, ix["vanster"]))
    # 1e-5: momentet samplas i 41 punkter per element, sa toppens exakta
    # lage traffas nagot olika. Det gamla max|M|-mattet varierade 74 %.
    assert varden[16][1] == pytest.approx(varden[8][1], rel=1e-5)
    assert varden[40][1] == pytest.approx(varden[8][1], rel=1e-5)
    assert varden[16][0] == pytest.approx(varden[8][0], rel=0.02)
    assert varden[40][0] == pytest.approx(varden[8][0], rel=0.02)


def test_hanbjalken_sanker_nocken_trots_att_den_styvar_upp():
    """
    Motintuitivt men riktigt: hanbjalken HINDRAR sparrarna fran att boja
    sig inat, sa i stallet roterar de utat kring takfoten -- och da
    sjunker nocken mer an utan hanbjalke. Utbojningen (kordaavvikelsen)
    minskar anda, se testet ovan. Lases har for att ingen ska "ratta"
    det till fel hall.
    """
    fr_utan, ix_utan = b1(h_hb=None)
    fr_med, ix_med = b1(h_hb=H_HB)
    assert abs(fr_med.node_disp(ix_med["apex"])[1]) > \
        abs(fr_utan.node_disp(ix_utan["apex"])[1])


def test_hanbjalken_ar_ledad_och_tryckt():
    """Andmomenten ar noll i lederna och normalkraften ar TRYCK for
    nedatriktad taklast (hanbjalken hindrar sparrarna att sjunka)."""
    fr, ix = b1()
    x, N, V, M = fr.internal(ix["hanbjalke"][0], npts=11)
    assert abs(M[0]) < 1e-9
    x, N, V, M = fr.internal(ix["hanbjalke"][-1], npts=11)
    assert abs(M[-1]) < 1e-9
    assert N[0] < 0


def test_underram_ar_dragband():
    """Taklasten spanner underramen: dragkraft i mitten av spannet."""
    fr, ix = b1(w_tak=W, w_golv=0.0)
    e_mitt = ix["underram"][len(ix["underram"]) // 2]
    _, N, _, _ = fr.internal(e_mitt)
    assert N[0] > 0.1


def test_golvlast_ger_nedbojning_mellan_fritt_upplagd_och_inspand():
    """
    Bara golvlast: underramens mittnedbojning ligger mellan den fritt
    upplagda (5wL^4/384EI) och den fullt inspanda (wL^4/384EI) --
    stodbenen och taket ger en partiell inspanning av andarna.
    """
    w = 1.5
    fr, ix = b1(w_tak=0.0, w_golv=w)
    mitt = ix["underram_noder"][len(ix["underram_noder"]) // 2]
    u = abs(fr.node_disp(mitt)[1])
    u_fri = 5 * w * L**4 / (384 * EI)
    u_fast = w * L**4 / (384 * EI)
    assert u_fast * 0.99 < u < u_fri * 1.01


def test_stodbenen_far_moment_av_taklasten():
    """Horisontalkraften vid takfot gar som bojning genom stodbenet --
    det ar darfor 5.3.5:s kontroll har ett M i knutpunkten."""
    fr, ix = b1()
    M_max = max(abs(M).max() for e in ix["stodben_v"]
                for M in [fr.internal(e)[3]])
    assert M_max > 0.5


def test_nockfjaderns_gransfall():
    fr_led, ix = b1()
    fr_mjuk, _ = b1(K_r=1e-9)
    fr_styv, _ = b1(K_r=1e9)
    fr_helstyv, _ = b1(nock_styv=True)
    u = lambda fr: fr.node_disp(ix["apex"])[1]          # noqa: E731
    assert u(fr_mjuk) == pytest.approx(u(fr_led), rel=1e-6)
    assert u(fr_helstyv) == pytest.approx(u(fr_styv), rel=1e-4)
    assert abs(u(fr_helstyv)) < abs(u(fr_led))


def test_hanbjalke_utanfor_sparren_ger_fel():
    with pytest.raises(ValueError):
        takstol_b1(L, ALPHA, H_STOD, EA, EI, h_hanbjalke=10.0)
    with pytest.raises(ValueError):
        takstol_b1(L, ALPHA, 0.0, EA, EI)
