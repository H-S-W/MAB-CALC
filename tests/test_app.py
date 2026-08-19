"""
Smoktest av webbgranssnittet med Streamlits egen AppTest.

AppTest kor app.py utan browser och utan server, sa hela formularet och
redovisningen exekveras pa riktigt. Det fangar det som ett importtest inte
gor: en widget med fel argument, ett falt som inte finns i projektfilen, en
formatterare som kraschar.

Det viktigaste testet ar test_appen_ger_samma_siffror_som_berakningen. Utan
det kan granssnittet tysta visa ett annat val an projektfilen anger --
vilket det ocksa gjorde: balkvaljarens alternativ ar Balk-objekt, sa en
uppslagning pa strangen "H300" foll tillbaka pa forsta balken i serien och
appen raknade pa H200.

Testerna hoppas over om streamlit inte ar installerat, sa att
berakningskarnan gar att testa utan granssnittsberoenden.
"""

import tomllib
from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="streamlit ar inte installerat")

from streamlit.testing.v1 import AppTest      # noqa: E402

import berakning                              # noqa: E402
import material                               # noqa: E402

ROT = Path(__file__).parent.parent
APP = str(ROT / "app.py")
PROJEKTFIL = ROT / "input" / "projekt.toml"


STEG2 = "2. Mått, ritning och resultat"


# Testerna far ett EGET autospar (miljovariabeln las av app.py) --
# annars raderar varje svitkorning utvecklarens pagaende appsession.
import os                                                    # noqa: E402
import tempfile                                              # noqa: E402
AUTOSPAR = Path(tempfile.gettempdir()) / "takstol_test_autospar.json"
os.environ["TAKSTOL_AUTOSPAR"] = str(AUTOSPAR)


def kor_appen(steg=STEG2):
    """
    Appen ar uppdelad i tva steg. Resultaten och ritningarna ligger i
    steg 2, sa testerna gar dit om inget annat sags.

    Autosparet raderas forst: testerna ska alltid utga fran
    projektfilen, inte fran vad utvecklaren rakade mata in senast --
    annars beror test_appen_ger_samma_siffror_som_berakningen pa
    maskinens tillstand.
    """
    AUTOSPAR.unlink(missing_ok=True)
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    if steg != at.radio[0].value:
        at.radio[0].set_value(steg).run()
    return at


@pytest.fixture(scope="module")
def app():
    return kor_appen()


def metric(at, etikett):
    return next(m for m in at.metric if m.label == etikett).value


def pct(u):
    """Samma procentformat som app.pct -- visningen jamfors exakt."""
    return f"{u * 100:.0f} %"


def _kvot(varde):
    """Procentstrang -> kvot (for jamforelser i testerna)."""
    return float(varde.replace("%", "").strip()) / 100.0


def test_appen_startar_utan_undantag(app):
    assert not app.exception, app.exception


def test_appen_visar_ingen_felruta_med_projektfilens_varden(app):
    """
    Standardvalen i input/projekt.toml ska ga rakt igenom. Dyker det upp ett
    st.error har ar det berakningen som avvisar kombinationen.
    """
    assert list(app.error) == [], [e.value for e in app.error]


def test_utnyttjandet_redovisas(app):
    etiketter = [m.label for m in app.metric]
    for vantad in ("Värsta utnyttjande", "Balken", "Nockförbandet",
                   "Upplaget", "Nedböjning"):
        assert vantad in etiketter, etiketter


def test_sammanfattningen_visar_varsta_av_alla_kontroller(app):
    """
    Toppraden ar max over balk, forband och nedbojning. Upplaget redovisas
    SEPARAT (anvandarbeslut 2026-08-18) i sin egen metric och via
    varningsbanderollen nar det overskrids -- det ingar inte i toppraden.
    """
    varden = {m.label: _kvot(m.value) for m in app.metric}
    assert varden["Värsta utnyttjande"] == pytest.approx(
        max(varden["Balken"], varden["Nockförbandet"],
            varden["Nedböjning"]), abs=0.001)
    assert varden["Upplaget"] > varden["Värsta utnyttjande"]


def test_balkkontrollen_redovisas_med_referenser(app):
    """
    Varje kontroll ska ha sin ETA- eller EC5-referens synlig i tabellen, sa
    att det gar att folja var talet kommer fran.
    """
    with open(PROJEKTFIL, "rb") as fh:
        vantat = berakning.kor(tomllib.load(fh))

    namn = {k.namn for k in vantat.balkkontroller}
    assert "Bojning" in namn and "Tvarkraft" in namn
    assert all(k.referens for k in vantat.balkkontroller)
    # och samma siffra som karnan raknar fram
    assert _kvot(next(m for m in app.metric if m.label == "Balken").value) \
        == pytest.approx(vantat.varsta_balkkontroll.utnyttjande, abs=0.001)


def test_appen_ger_samma_siffror_som_berakningen(app):
    """
    Granssnittet ska starta med precis det projektfilen anger och rakna
    samma sak som run.py. Skiljer sig nagot har visar appen ett annat fall
    an det anvandaren tror -- det tystaste och varsta felet ett sadant
    granssnitt kan ha.
    """
    with open(PROJEKTFIL, "rb") as fh:
        vantat = berakning.kor(tomllib.load(fh))

    assert metric(app, "Nockförbandet") == pct(vantat.forband_utnyttjande)
    assert metric(app, "Balken") == \
        pct(vantat.varsta_balkkontroll.utnyttjande)
    assert metric(app, "Värsta utnyttjande") == \
        pct(vantat.varsta_utnyttjande)


def test_appen_startar_pa_balken_i_projektfilen(app):
    """
    Regressionstest for _balkindex. Balkvaljaren ska visa projektfilens balk,
    inte forsta balken i serien.
    """
    with open(PROJEKTFIL, "rb") as fh:
        vantad = tomllib.load(fh)["geometri"]["balk"]
    valjaren = next(s for s in app.selectbox if s.label == "Balk")
    assert valjaren.value.namn == vantad


def test_sidostodsvarningen_syns_for_momentstyv_nock(app):
    """
    Med momentstyv nock och utan sidostod av underflansen ska varningen om
    ETA tab. 19 finnas i redovisningen. Det ar den kontrollen som valdes:
    varna och rakna vidare.
    """
    text = " ".join(w.value for w in app.warning)
    assert "UNDERFLÄNSEN" in text
    assert "tab. 19" in text


def test_alla_materialval_finns_i_formularet(app):
    """
    Materialvalen fylls ur biblioteken, inte ur hardkodade listor.
    De ligger pa steg 2 (matt och utformning); nedbojningskravet hor till
    forutsattningarna och provas separat nedan.

    Lastvaraktigheten ar inget val: k_mod bestams per lastkombination
    (EN 1995-1-1 3.1.3(2)).
    """
    etiketter = [s.label for s in app.selectbox]
    for vantad in ("Balk", "Flänskvalitet",
                   "Skivmaterial", "Förbindare mot fläns",
                   "Förbindare mot liv"):
        assert vantad in etiketter, etiketter

    balkar = next(s for s in app.selectbox if s.label == "Balk")
    assert len(balkar.options) == 72     # hela ETA-biblioteket i EN valjare


def test_steg1_har_forutsattningarna():
    """
    Steg 1 ska bara innehalla det som INTE beror pa matten: plats,
    laster, klasser och nedbojningskrav. Takstolstypen ar fast:
    momentstyv nock.
    """
    at = kor_appen(steg="1. Plats, laster och typ")
    assert not at.exception
    etiketter = [s.label for s in at.selectbox]
    assert "Nedböjningskrav" in etiketter
    assert "Terrängtyp" in etiketter
    # matten hor inte hemma har
    assert "Balk" not in etiketter
    # typvalet ar BORTTAGET: appen ar slimad till momentstyv nock
    # (anvandarbeslut 2026-08-19); ledad/b1 lever i berakningskarnan
    # och run.py --jamfor, inte i granssnittet
    assert not [r for r in at.radio if r.label == "Typ"]


def test_hogre_balk_ger_hogre_kapacitet_i_forbandet():
    """
    Nockforbandets havarm ar c_flans = h - h_flans, sa en hogre balk ger
    hogre momentkapacitet i spikgrupperna. Det ar det yttersta beviset pa
    att granssnittet ar kopplat till biblioteket.
    """
    at = kor_appen()
    lag = metric(at, "Nockförbandet")

    hog = [b for b in material.balkar(liv="osb", serie="H") if b.h == 500][0]
    next(s for s in at.selectbox if s.label == "Balk").set_value(hog).run()
    assert not at.exception, at.exception
    assert metric(at, "Nockförbandet") != lag


def test_balkvaljaren_rymmer_bada_livmaterialen():
    """EN valjare over hela biblioteket (2026-08-19): bade OSB- och
    spanskivebalkar ska finnas, och valet skrivs till cfg sa det
    autosparas -- de gamla Serie/Liv-valen gjorde inte det."""
    at = kor_appen()
    valjaren = next(s for s in at.selectbox if s.label == "Balk")
    namn = [o.split()[0] for o in valjaren.options]
    assert "H300" in namn and "H300s" in namn
    val = next(o for o in valjaren.options if o.split()[0] == "H300s")
    at2 = valjaren.set_value(val).run()
    assert not at2.exception, at2.exception
    balk = next(s for s in at2.selectbox if s.label == "Balk").value
    assert balk.namn == "H300s" and balk.liv == "spanskiva"


def test_osb_skiva_ger_bada_metoderna():
    """
    Med OSB/3 som skivmaterial finns f_t,0 deklarerad i EN 12369-1, sa
    jamforelsen mot handbokens f_m ska dyka upp som en st.info.
    """
    at = kor_appen()
    next(s for s in at.selectbox
         if s.label == "Skivmaterial").set_value("osb3").run()
    assert not at.exception, at.exception

    text = " ".join(i.value for i in at.info)
    assert "handbokens f_m" in text and "M_Rd" in text


def test_plywood_redovisar_f_t_90_valet(app):
    """
    Handbokens plywood raknas numera i planet med f_t,90 = 7,0 MPa
    (deklarerad i 5.3.4.2). Valet ska synas med kalla och motivering --
    det ar den svagare riktningen, konservativt oavsett montering.
    """
    text = " ".join(w.value for w in app.warning)
    assert "f_t,90" in text and "5.3.4.2" in text


def test_hb_balk_varnar_for_saknad_dragkapacitet():
    """
    HB med OSB-liv har ingen anvandbar N_tk i ETA tab. 11, se ERRATA punkt 4.
    Valjer man den serien ska sidopanelen saga det.
    """
    at = kor_appen()
    valjaren = next(s for s in at.selectbox if s.label == "Balk")
    val = next(o for o in valjaren.options if o.split()[0] == "HB300")
    at2 = valjaren.set_value(val).run()
    assert not at2.exception, at2.exception
    assert any("dragkapacitet" in w.value for w in at2.warning)


def test_inmatningen_overlever_en_omladdning():
    """
    Autosparet: andra spannvidden, ladda om (ny AppTest = ny session,
    precis som en siduppdatering), och vardet ska sta kvar. Darefter
    ska "Las om projektfilen" glomma det.
    """
    at = kor_appen()                              # raderar autosparet
    w = next(n for n in at.number_input if n.label == "Spännvidd [m]")
    at = w.set_value(12.5).run()
    assert AUTOSPAR.exists()

    # "omladdning": helt ny apptest-session, autosparet lamnas kvar
    at2 = AppTest.from_file(APP, default_timeout=90)
    at2.run()
    if at2.radio[0].value != STEG2:
        at2.radio[0].set_value(STEG2).run()
    w2 = next(n for n in at2.number_input if n.label == "Spännvidd [m]")
    assert w2.value == 12.5
    assert any("återupptogs" in c.value for c in at2.caption)

    knapp = next(b for b in at2.button
                 if b.label == "Läs om projektfilen")
    at3 = knapp.click().run()
    assert not AUTOSPAR.exists()

    AUTOSPAR.unlink(missing_ok=True)              # stada efter sig
