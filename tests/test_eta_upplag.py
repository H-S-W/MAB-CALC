"""
Verifiering av src/upplag.py mot ETA 12/0018 tab. 13 och 14.

ETA:n innehaller tva tabeller med fardigraknade upplagskapaciteter for
"preferred sizes" -- i praktiken ett facit pa ca 200 varden som metoden i
ekv. 3-5 med tab. 6-9 maste reproducera. Har kontrolleras ett systematiskt
URVAL: alla fyra serierna, laga och hoga balkar, alla fyra
upplagslangderna, bada lagena och bada forstarkningsfallen -- inklusive
horndallen dar k_6 (H450/500), k_7 (forstarkta HB) och interpolerade
k_A/k_B-varden styr. Urvalet ar 60+ varden; tabellcellerna som inte ar med
ar mellanliggande hojder i samma monster.

Nyckelupptackt som testerna later fast: tabellkolumnen L1 = 95 och 145 mm
ar INTE tabellpunkter i tab. 7/8 (som har 45/70/100/150) -- ETA:n har
interpolerat linjart, och vid L1 = 45 for mittstod EXTRAPOLERAT (tab. 8:s
mittdel borjar vid 70). Metoden maste gora likadant for att traffa facit.

Tolerans 1 % pa varje varde: tabellen ar avrundad till 0,1 kN.
"""

import pytest

import material
import upplag


def F_k(balknamn, L1, lage="and", forstarkning=False, punktlast=False):
    return upplag.kapacitet(material.balk(balknamn), L1, lage=lage,
                            forstarkning=forstarkning,
                            punktlast=punktlast).F_k


L1_KOLUMNER = [45.0, 70.0, 95.0, 145.0]


def _kolla(balknamn, tryckta, **fall):
    for L1, tryckt in zip(L1_KOLUMNER, tryckta):
        varde = F_k(balknamn, L1, **fall)
        assert varde == pytest.approx(tryckt, rel=0.011), \
            f"{balknamn} L1={L1:.0f} {fall}: {varde:.2f} mot tryckt {tryckt}"


# ---------------------------------------------------------------------------
# Tab. 14 -- jamnt utbredd last UTAN punktlast over stodet
# (det normala fallet for en takstol pa vaggkron)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("balk,tryckta", [
    # Andupplag utan forstarkning: (L1/45)^0.5 * a * k_6.
    # H200-H400 ar en enda tryckt rad eftersom k_6 = 1 under 400 mm.
    ("H200", [9.0, 11.2, 13.1, 16.2]),
    ("H400", [9.0, 11.2, 13.1, 16.2]),
    ("H450", [8.6, 10.8, 12.6, 15.5]),      # k_6 = 0.96
    ("H500", [7.6, 9.4, 11.0, 13.6]),       # k_6 = 0.84
    ("HM300", [9.5, 11.8, 13.8, 17.1]),
    ("HM500", [8.0, 10.0, 11.6, 14.3]),
    ("HI250", [10.5, 13.1, 15.3, 18.8]),
    ("HI500", [8.8, 11.0, 12.8, 15.8]),
    ("HB250", [12.0, 15.0, 17.4, 21.5]),
    ("HB500", [10.1, 12.6, 14.6, 18.1]),
])
def test_tab14_andupplag_utan_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="and")


@pytest.mark.parametrize("balk,tryckta", [
    # Andupplag MED forstarkning: (L1/45)^0.5 * a * k_B * k_7.
    # k_B interpoleras i bade h och L1; kolumnen 145 ligger mellan
    # tabellpunkterna 100 och 150.
    ("H200", [11.7, 13.8, 15.1, 16.3]),
    ("H300", [12.5, 14.7, 16.1, 17.4]),
    ("H500", [14.1, 16.5, 18.1, 19.6]),
    ("HM300", [13.2, 15.5, 17.0, 18.4]),
    ("HM500", [14.8, 17.5, 19.1, 20.7]),
    ("HI200", [13.7, 16.1, 17.6, 19.0]),
    ("HI500", [16.4, 19.3, 21.2, 22.9]),
    # HB-serien ar den enda dar k_7 avviker fran 1,0 (tab. 9)
    ("HB200", [15.6, 18.4, 20.1, 21.8]),    # k_7 = 1.00 under 400
    ("HB400", [18.2, 21.5, 23.5, 25.4]),    # k_7 = 1.03
    ("HB500", [21.9, 25.8, 28.3, 30.6]),    # k_7 = 1.17
])
def test_tab14_andupplag_med_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="and", forstarkning=True)


@pytest.mark.parametrize("balk,tryckta", [
    # Mittstod utan forstarkning: k_A = 1 utan punktlast -> en rad per serie
    ("H300", [14.0, 17.5, 20.3, 25.1]),
    ("HM300", [15.0, 18.7, 21.8, 26.9]),
    ("HI300", [17.0, 21.2, 24.7, 30.5]),
    ("HB300", [21.0, 26.2, 30.5, 37.7]),
])
def test_tab14_mittstod_utan_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="mitt")


@pytest.mark.parametrize("balk,tryckta", [
    # Mittstod MED forstarkning. Vardet vid L1 = 45 kraver EXTRAPOLERING
    # av k_B, vars mittdel borjar forst vid 70 mm -- 18.2 for H200 gar
    # bara att traffa med lutningen fran 70-100-intervallet forlangd.
    ("H200", [18.2, 21.8, 24.4, 27.6]),
    ("H300", [19.4, 23.3, 26.0, 29.5]),
    ("H500", [21.9, 26.2, 29.3, 33.2]),
    ("HM300", [20.8, 25.0, 27.9, 31.6]),
    ("HB300", [29.1, 34.9, 39.1, 44.2]),
    ("HB500", [38.4, 46.0, 51.4, 58.3]),    # k_7 = 1.17 aven vid mittstod
])
def test_tab14_mittstod_med_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="mitt", forstarkning=True)


# ---------------------------------------------------------------------------
# Tab. 13 -- jamnt utbredd last MED punktlast over stodet
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("balk,tryckta", [
    # Andupplag utan forstarkning: har ar k_A aktiv (tab. 7)
    ("H250", [9.0, 11.2, 13.1, 16.2]),      # k_A = 1.0 vid 250
    ("H300", [9.0, 11.1, 12.8, 15.4]),
    ("H400", [9.0, 10.8, 12.1, 13.8]),
    ("H450", [8.5, 10.1, 11.3, 12.5]),      # k_A och k_6 samtidigt
    ("H500", [7.3, 8.6, 9.5, 10.3]),
])
def test_tab13_andupplag_utan_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="and", punktlast=True)


@pytest.mark.parametrize("balk,tryckta", [
    # Med punktlast och forstarkning ar k_B = 1 och k_6 = 1: kapaciteten
    # beror bara pa serien -- en tryckt rad per serie, oavsett hojd.
    ("H300", [9.0, 11.2, 13.1, 16.2]),
    ("H500", [9.0, 11.2, 13.1, 16.2]),
    ("HM400", [9.5, 11.8, 13.8, 17.1]),
    ("HI400", [10.5, 13.1, 15.3, 18.8]),
    ("HB400", [12.0, 15.0, 17.4, 21.5]),    # k_7 = 1 MED punktlast
])
def test_tab13_andupplag_med_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="and", forstarkning=True, punktlast=True)


@pytest.mark.parametrize("balk,tryckta", [
    # Mittstod utan forstarkning med punktlast: k_A:s mittdel
    ("H250", [14.0, 17.5, 20.3, 25.1]),
    ("H350", [14.0, 17.1, 18.9, 23.1]),
    ("H400", [14.0, 16.8, 18.2, 22.1]),
    ("H500", [14.0, 16.2, 16.7, 20.1]),
])
def test_tab13_mittstod_utan_forstarkning(balk, tryckta):
    _kolla(balk, tryckta, lage="mitt", punktlast=True)


# ---------------------------------------------------------------------------
# Reglerna runt formeln
# ---------------------------------------------------------------------------

def test_utstick_hojer_kapaciteten_vid_andupplag():
    """ekv. 5: delta_a = 4y/(h/2). y = 150 pa en H300 ger a = 9 + 4 kN."""
    utan = upplag.kapacitet(material.balk("H300"), 45.0, y=0.0)
    med = upplag.kapacitet(material.balk("H300"), 45.0, y=150.0)
    assert med.F_k == pytest.approx(utan.F_k + 4.0, rel=1e-6)


def test_stort_utstick_raknas_som_mittstod():
    """y > h -> mittstodsvarden (som ar hogre)."""
    res = upplag.kapacitet(material.balk("H300"), 70.0, y=350.0)
    assert res.lage == "mitt"
    assert res.F_k == pytest.approx(17.5, rel=0.011)


def test_upplagslangden_kapas_vid_150_respektive_200():
    """Effektiv L1: hogst 150 vid andupplag, hogst 200 vid mittstod."""
    a_150 = F_k("H300", 150.0)
    a_300 = F_k("H300", 300.0)
    assert a_300 == pytest.approx(a_150, rel=1e-9)

    m_200 = F_k("H300", 200.0, lage="mitt")
    m_400 = F_k("H300", 400.0, lage="mitt")
    assert m_400 == pytest.approx(m_200, rel=1e-9)


def test_kortare_motstaende_upplag_styr():
    """Fotnot 2: ar L2 < L1 anvands L2."""
    res = upplag.kapacitet(material.balk("H300"), 145.0, L2=70.0)
    assert res.F_k == pytest.approx(F_k("H300", 70.0), rel=1e-9)


def test_for_kort_upplag_far_en_anmarkning():
    res = upplag.kapacitet(material.balk("H300"), 40.0)
    assert any("45 mm" in a for a in res.anmarkningar)


def test_tvarkraften_ar_ett_tak():
    """
    ETA:s fotnot: F_d <= V_d vid andupplag. En H200 med langt forstarkt
    upplag har hogre upplagstryck an tvarkraftskapacitet -- da ska
    tvarkraften styra och det ska sagas.
    """
    res = upplag.kapacitet(material.balk("H200"), 145.0, forstarkning=True)
    V_Rd = material.balk("H200").V_k * 0.70 / 1.30
    assert res.F_Rd == pytest.approx(min(res.F_Rd_tryck, V_Rd))
    if res.F_Rd < res.F_Rd_tryck:
        assert any("tvarkraften begransar" in a for a in res.anmarkningar)


def test_kmod_raden_valjs_enligt_fotnoten_i_tabell_17():
    """
    Punktlast utan forstarkning vid h >= 250 (andupplag) -> tvarkraftens
    k_mod. Annars bojningens.
    """
    b = material.balk("H300")
    med_punkt = upplag.kapacitet(b, 45.0, punktlast=True)
    assert med_punkt.k_mod_rad == "tvarkraft"
    assert med_punkt.k_mod == 0.70                      # OSB-liv, kk1 medel

    utan_punkt = upplag.kapacitet(b, 45.0)
    assert utan_punkt.k_mod_rad == "bojning"
    assert utan_punkt.k_mod == 0.80

    lag = upplag.kapacitet(material.balk("H200"), 45.0, punktlast=True)
    assert lag.k_mod_rad == "bojning"                   # h < 250


def test_spanskiveliv_ger_annat_tvarkraftstak():
    """Taket raknas med tvarkraftens k_mod, som beror pa livmaterialet."""
    osb = upplag.kapacitet(material.balk("H300"), 45.0)
    span = upplag.kapacitet(material.balk("H300s"), 45.0)
    assert osb.V_Rd_tak == pytest.approx(20.5 * 0.70 / 1.30, rel=1e-6)
    assert span.V_Rd_tak == pytest.approx(23.1 * 0.65 / 1.30, rel=1e-6)


def test_fotnot_3_grunda_balkar_vid_mittstod():
    """
    ETA s. 9, fotnot 3 till avsn. 1.2.3: "For situations when h <= 220 mm,
    bearing capacity shall be calculated for L1 = 150 mm." Vid mittstod
    kapas L1 annars vid 200 mm; for h <= 220 galler 150 mm.
    """
    import material
    import upplag as U

    for namn, forvantad in (("H200", 150.0), ("H220", 150.0),
                            ("H240", 200.0), ("H300", 200.0)):
        b = material.balk(namn)
        kap = U.kapacitet(b, 250.0, lage="mitt", klimatklass=1,
                          varaktighet="medel")
        assert kap.detaljer["L1_eff"] == pytest.approx(forvantad), namn

    # andupplaget kapas alltid vid 150 mm, oavsett hojd
    for namn in ("H200", "H300"):
        kap = U.kapacitet(material.balk(namn), 250.0, lage="and",
                          klimatklass=1, varaktighet="medel")
        assert kap.detaljer["L1_eff"] == pytest.approx(150.0)
