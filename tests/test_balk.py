"""
Verifiering av src/balk.py -- balkens egen barformaga i brottgranstillstand.

Kapaciteterna ar enkla multiplikationer av ETA-varden, sa det testerna
faktiskt behover sakra ar
  - att RATT k_mod anvands i rätt kontroll (bojning och tvarkraft har olika,
    ETA tab. 17, och tvarkraftens beror pa livmaterialet),
  - att k_h inte laggs till en andra gang ovanpa tabellernas M_k,
  - att knackningsformlerna i EN 1995-1-1 6.3.2 ar rätt implementerade, och
  - att den snabba skanningsfunktionen ger samma svar som den fullstandiga
    kontrollen.
"""

import pytest

import balk as B
import material

BALK = material.balk("H300")
K_MOD_B = 0.80          # bojning, klimatklass 1, medellang last
K_MOD_V = 0.70          # tvarkraft, OSB-liv, klimatklass 1, medellang last
GAMMA = 1.30            # handboken s. 232
L_EF = 5.61             # sparrelangd for 10 m spann och 27 grader


# ---------------------------------------------------------------------------
# Dimensionerande barformagor
# ---------------------------------------------------------------------------

def test_momentkapaciteten_ar_M_k_gangar_kmod_delat_gamma():
    """12,7 * 0,8/1,3 = 7,82 kNm. Ingen extra k_h -- den ar redan inbakad."""
    assert B.M_Rd(BALK, K_MOD_B, GAMMA) == pytest.approx(12.7 * 0.8 / 1.3)
    assert B.M_Rd(BALK, K_MOD_B, GAMMA) == pytest.approx(7.815, abs=0.001)


def test_tvarkraftskapaciteten_anvander_tvarkraftens_egen_kmod():
    """
    20,5 * 0,7/1,3 = 11,04 kN. Anvands bojningens k_mod = 0,8 av misstag
    blir det 12,62 kN, alltsa 14 % for hogt. Det ar det latta felet.
    """
    assert B.V_Rd(BALK, K_MOD_V, GAMMA) == pytest.approx(11.038, abs=0.001)
    assert B.V_Rd(BALK, K_MOD_V, GAMMA) < B.V_Rd(BALK, K_MOD_B, GAMMA)


def test_spanskiveliv_ger_annan_tvarkraftskapacitet():
    """
    H300s har hogre V_k (23,1 mot 20,5) men lagre k_mod for tvarkraft
    (0,65 mot 0,70). Netto blir spanskivan anda nagot starkare har.
    """
    span = material.balk("H300s")
    osb_Rd = B.V_Rd(BALK, 0.70, GAMMA)
    span_Rd = B.V_Rd(span, 0.65, GAMMA)
    assert span.V_k > BALK.V_k
    assert span_Rd > osb_Rd


def test_tryck_och_dragkapacitet():
    assert B.N_c_Rd(BALK, K_MOD_B, GAMMA) == pytest.approx(116.2 * 0.8 / 1.3)
    assert B.N_t_Rd(BALK, K_MOD_B, GAMMA) == pytest.approx(92.0 * 0.8 / 1.3)


def test_dragkapacitet_vagras_for_hb_med_osb_liv():
    """docs/ERRATA.md punkt 4."""
    with pytest.raises(ValueError, match="ERRATA"):
        B.N_t_Rd(material.balk("HB300"), K_MOD_B, GAMMA)


# ---------------------------------------------------------------------------
# Knackning, EN 1995-1-1 6.3.2
# ---------------------------------------------------------------------------

def test_knacklasten_ar_eulers():
    """N_crit = pi^2 * EI_05 / L_ef^2 med EI_05 = 0,67 * 929 kNm2."""
    from math import pi
    vantat = pi**2 * (929 * 0.67) / L_EF**2
    assert B.N_crit(BALK, L_EF, 0.67) == pytest.approx(vantat)
    assert B.N_crit(BALK, L_EF, 0.67) == pytest.approx(195.1, abs=0.2)


def test_knacklasten_avtar_med_kvadraten_pa_langden():
    dubbel = B.N_crit(BALK, 2 * L_EF, 0.67)
    assert dubbel == pytest.approx(B.N_crit(BALK, L_EF, 0.67) / 4)


def test_lambda_rel_ur_deklarerade_storheter():
    """
    lambda_rel = sqrt(N_ck / N_crit). Skrivningen i kapaciteter i stallet
    for spanningar gor att varken A eller f_c,0,k behover gissas.
    """
    from math import sqrt
    lam = B.lambda_rel(BALK, L_EF, 0.67)
    assert lam == pytest.approx(sqrt(116.2 / B.N_crit(BALK, L_EF, 0.67)))
    assert lam == pytest.approx(0.772, abs=0.002)


def test_kc_ar_ett_for_korta_stanger():
    """EC5 6.3.2(3): for lambda_rel <= 0,3 sker ingen knackningsreduktion."""
    assert B.k_c(0.0) == 1.0
    assert B.k_c(0.3) == 1.0
    assert B.k_c(0.30001) < 1.0


def test_kc_minskar_med_slankheten():
    varden = [B.k_c(lam) for lam in (0.4, 0.8, 1.2, 1.6, 2.0)]
    assert varden == sorted(varden, reverse=True)
    assert all(0 < v <= 1 for v in varden)


def test_kc_for_projektets_sparre():
    """lambda_rel = 0,772 med beta_c = 0,2 ger k_c = 0,841."""
    assert B.k_c(0.772, 0.2) == pytest.approx(0.841, abs=0.002)


def test_limtra_far_gynnsammare_beta_c():
    """EC5 ekv. 6.29: beta_c = 0,1 for limtra mot 0,2 for massivt tra."""
    assert B.k_c(1.0, beta_c=0.1) > B.k_c(1.0, beta_c=0.2)


def test_femprocentilkvoten_paverkar_knackningen():
    """
    ETA tab. 5 ger MEDELvardet av E_f. EC5 6.3.2 kraver 5-percentilen.
    Anvands medelvardet rakt av blir knacklasten 49 % for hog.
    """
    med_medel = B.N_crit(BALK, L_EF, 1.0)
    med_05 = B.N_crit(BALK, L_EF, 0.67)
    assert med_medel / med_05 == pytest.approx(1 / 0.67, rel=1e-9)
    assert B.k_c(B.lambda_rel(BALK, L_EF, 1.0)) > \
        B.k_c(B.lambda_rel(BALK, L_EF, 0.67))


# ---------------------------------------------------------------------------
# Sidostod
# ---------------------------------------------------------------------------

def test_sidostodet_provas_mot_eta_tabell_19():
    """H-serien: hogst 350 mm. HB-serien: hogst 1000 mm."""
    assert B.sidostod_racker(BALK, 300.0)
    assert B.sidostod_racker(BALK, 350.0)
    assert not B.sidostod_racker(BALK, 351.0)
    assert B.sidostod_racker(material.balk("HB300"), 900.0)


def test_inget_sidostod_racker_inte():
    """0 mm betyder inget stod, inte oandligt tatt stod."""
    assert not B.sidostod_racker(BALK, 0.0)
    assert not B.sidostod_racker(BALK, -1.0)


# ---------------------------------------------------------------------------
# Samlad kontroll
# ---------------------------------------------------------------------------

def kontroller(M=-9.11, V=-8.32, N=-17.48):
    return B.kontrollera(BALK, M, V, N, L_EF, K_MOD_B, K_MOD_V, GAMMA)


def test_kontrollerna_som_gors_vid_tryck():
    namn = [k.namn for k in kontroller()]
    assert namn == ["Bojning", "Tvarkraft", "Axialkraft, tryck",
                    "Bojning + tryck med knackning"]


def test_kontrollerna_som_gors_vid_drag():
    namn = [k.namn for k in kontroller(N=+17.48)]
    assert namn == ["Bojning", "Tvarkraft", "Axialkraft, drag",
                    "Bojning + drag"]


def test_projektets_snitt_ar_last():
    """
    Regressionslas pa det snitt som styr i projektfilen: nocken med
    M = -9,11 kNm, N = -17,48 kN tryck och V = -8,32 kN.
    """
    k = {x.namn: x for x in kontroller()}
    assert k["Bojning"].utnyttjande == pytest.approx(1.165, abs=0.002)
    assert k["Tvarkraft"].utnyttjande == pytest.approx(0.754, abs=0.002)
    assert k["Axialkraft, tryck"].utnyttjande == pytest.approx(0.244,
                                                               abs=0.002)
    assert k["Bojning + tryck med knackning"].utnyttjande == \
        pytest.approx(1.456, abs=0.003)


def test_teckenkonventionen_pa_normalkraften():
    """
    N positiv = drag, som i ram.internal(). Byter man tecken ska det bli en
    dragkontroll, inte en tryckkontroll.
    """
    assert any("tryck" in k.namn for k in kontroller(N=-10.0))
    assert any("drag" in k.namn for k in kontroller(N=+10.0))


def test_momentets_tecken_spelar_ingen_roll_for_kapaciteten():
    """
    Balken har samma momentkapacitet i bada riktningarna. Teckenbytet spelar
    roll for VILKEN FLANS som ar tryckt, och det hanteras av
    sidostodskontrollen -- inte har.
    """
    positivt = {k.namn: k.utnyttjande for k in kontroller(M=+9.11)}
    negativt = {k.namn: k.utnyttjande for k in kontroller(M=-9.11)}
    assert positivt == negativt


def test_kort_stang_kvadrerar_interaktionen():
    """
    EC5 6.3.2(3): vid lambda_rel <= 0,3 anvands (N/N_Rd)^2 + M/M_Rd, alltsa
    ett gynnsammare uttryck. En mycket kort knacklangd ska ge det.
    """
    kort = B.kontrollera(BALK, -5.0, -5.0, -20.0, 0.5, K_MOD_B, K_MOD_V,
                         GAMMA)
    interaktion = next(k for k in kort if k.namn.startswith("Bojning +"))
    assert interaktion.namn == "Bojning + tryck"
    assert "6.19" in interaktion.referens
    assert "kort" in " ".join(interaktion.anmarkningar)


def test_dragfallet_summerar_linjart():
    """EC5 6.2.3 ekv. 6.17 har ingen kvadrering."""
    k = {x.namn: x for x in kontroller(N=+17.48)}
    vantat = (k["Axialkraft, drag"].utnyttjande
              + k["Bojning"].utnyttjande)
    assert k["Bojning + drag"].utnyttjande == pytest.approx(vantat)


def test_hb_med_osb_liv_i_drag_ger_oandligt_utnyttjande():
    """
    Saknas dragkapaciteten ska kontrollen inte tysta hoppas over. Den ska
    misslyckas synligt och forklara varfor.
    """
    kk = B.kontrollera(material.balk("HB300"), -5.0, -5.0, +10.0, L_EF,
                       K_MOD_B, K_MOD_V, GAMMA)
    drag = next(k for k in kk if "drag" in k.namn)
    assert drag.utnyttjande == float("inf")
    assert not drag.ok
    assert "ERRATA" in drag.referens


def test_varsta_valjer_hogsta_utnyttjandet():
    kk = kontroller()
    assert B.varsta(kk).namn == "Bojning + tryck med knackning"
    assert B.varsta(kk).utnyttjande == max(k.utnyttjande for k in kk)


def test_ok_flaggan_gar_vid_ett():
    assert B.Kontroll("x", 1.0, "ref").ok
    assert not B.Kontroll("x", 1.0001, "ref").ok


# ---------------------------------------------------------------------------
# Snabbfunktionen for skanning ska ge samma svar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("M,V,N", [
    (-9.11, -8.32, -17.48),      # projektets nocksnitt
    (5.0, 3.0, -8.0),            # positivt moment, tryck
    (2.0, 1.0, 12.0),            # drag
    (0.0, 0.0, 0.0),             # olastat
    (-20.0, -25.0, -60.0),       # hart lastat
])
def test_utnyttjande_ger_samma_som_full_kontroll(M, V, N):
    """
    balk.utnyttjande() finns for att kunna skanna hundratals snitt langs
    sparrarna utan att bygga Kontroll-objekt. Den far inte kunna sacka isar
    fran kontrollera().
    """
    snabb = B.utnyttjande(BALK, M, V, N, L_EF, K_MOD_B, K_MOD_V, GAMMA)
    full = max(k.utnyttjande
               for k in B.kontrollera(BALK, M, V, N, L_EF, K_MOD_B, K_MOD_V,
                                      GAMMA))
    assert snabb == pytest.approx(full)


def test_utnyttjande_vagrar_ocksa_hb_i_drag():
    assert B.utnyttjande(material.balk("HB300"), -5.0, -5.0, +10.0, L_EF,
                         K_MOD_B, K_MOD_V, GAMMA) == float("inf")
