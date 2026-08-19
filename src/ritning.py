"""
Ritningar av det som beraknas: takstolens geometri och nockforbandets
spikbild med matt.

Modulen innehaller INGEN ingenjorslogik och inga materialvarden -- den
laser Resultat och cfg och ritar det som redan ar berakknat. Alla matt
som visas kommer ur berakningen, inte ur ritkoden.

Figurerna byggs med matplotlib.figure.Figure (inte pyplot), sa att de
gar att rita i Streamlit utan globalt tillstand.
"""

from math import cos, degrees, radians, sin, tan

from matplotlib.figure import Figure

# Farger: rita som en verkstadsritning, inte ett diagram.
FLANS = "#c8a165"
LIV = "#e8dcc0"
SKIVA = "#dfca8c"   # plywood -- skild fran flansens tan och livets beige
SPIK = "#1a1a1a"
MATT = "#666666"


def _mattlinje(ax, x1, y1, x2, y2, text, off=0, vertikal=False):
    """Mattlinje med pilar och text, som pa en ritning."""
    ax.annotate("", (x2, y2), (x1, y1),
                arrowprops=dict(arrowstyle="<->", color=MATT, lw=0.8))
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    ax.text(mx + (off if vertikal else 0), my + (0 if vertikal else off),
            text, ha="center", va="center", fontsize=7, color=MATT,
            rotation=90 if vertikal else 0,
            bbox=dict(fc="white", ec="none", pad=0.8))


def _riktning(alfa, hoger):
    """(axelriktning fran fogen och utat, normal) for en sparre."""
    import numpy as np
    if hoger:
        return (np.array([cos(alfa), -sin(alfa)]),
                np.array([sin(alfa), cos(alfa)]))
    return (np.array([-cos(alfa), -sin(alfa)]),
            np.array([-sin(alfa), cos(alfa)]))


def _vrid(x, y, alfa, hoger):
    """
    Spikkoordinat -> lage i nockens verkliga geometri.

    Delegerar till forband.vrid_till_nock -- SAMMA transform som
    nockfjadern K_r raknas med (EC5.K_rot_skarv_vriden), sa bild och
    siffra kommer ur exakt samma geometri. `hoger` behalls i signaturen
    for profilritningen men sparrtillhorigheten avgors av y:s tecken,
    precis som i berakningen.
    """
    import numpy as np

    from forband import vrid_till_nock
    if y == 0:                    # mattlinjernas startpunkt pa fogen
        y = 1e-9 if hoger else -1e-9
    return np.array(vrid_till_nock(x, y, alfa))


def _profil(alfa, hoger, d_lag, d_hog, langd):
    """
    Hornen for en del av sparren som ligger mellan de vinkelratta
    avstanden d_lag och d_hog fran balkaxeln, kapad i det LODRATA
    fogplanet.

    En punkt pa avstandet d fran axeln korsar fogplanet (x = 0) vid
    y = d/cos(alfa) -- oberoende av vilken sparre det galler. Darav
    kapytans horn. Att i stallet bygga en centrerad profil och flytta
    den i sidled ger en kapyta som INTE ligger i fogen; da korsar
    flansarna varandra vid nocken.
    """
    import numpy as np
    u, n = _riktning(alfa, hoger)
    c = cos(alfa)
    fjarr = langd * u
    return [np.array([0.0, d_hog / c]),
            fjarr + d_hog * n,
            fjarr + d_lag * n,
            np.array([0.0, d_lag / c])]


def _sparrhorn(alfa, hoger, h, langd, hojd=None):
    """Hela balkprofilen, centrerad kring axeln."""
    hh = (hojd if hojd is not None else h) / 2.0
    return _profil(alfa, hoger, -hh, hh, langd)


def _skivhorn(alfa, hojd, halvlangd):
    """
    Skivans kontur: EN flat skiva som spanner over vinkeln, alltsa
    unionen av de tva sparrarnas skivytor.
    """
    import numpy as np
    v = _sparrhorn(alfa, False, hojd, halvlangd)
    h = _sparrhorn(alfa, True, hojd, halvlangd)
    # uppifran och medsols: vanster ytterkant -> nock -> hoger ytterkant
    return [v[1], np.array([0.0, hojd / 2 / cos(alfa)]), h[1], h[2],
            np.array([0.0, -hojd / 2 / cos(alfa)]), v[2]]


def nockforband(res, cfg):
    """
    Nockforbandets spikbild i nockens VERKLIGA geometri: sparrarna moter
    varandra i en lodrat stotfog med taklutningen, och skivorna spanner
    over fogen.
    """
    import numpy as np
    from matplotlib.patches import Polygon

    balk = res.balk
    fb = cfg["forband"]
    s = fb["cc_forbindare"]
    alfa = radians(cfg["geometri"]["taklutning"])
    h, hf = balk.h, balk.h_flans

    fig = Figure(figsize=(6.4, 4.2), dpi=115)
    ax = fig.add_subplot(111)

    alla_y = [abs(y) for gr in res.grupper for _, y in gr.grupp.coords]
    y_max = max(alla_y) if alla_y else 100.0
    l_yt = _skivlangd(res, "flans", s) / 2
    l_liv = _skivlangd(res, "liv", s) / 2
    langd = max(y_max + 3 * s, l_yt + 25)

    # -- sparrarna -----------------------------------------------------
    for hoger in (False, True):
        u, n = _riktning(alfa, hoger)
        ax.add_patch(Polygon(_sparrhorn(alfa, hoger, h, langd),
                             closed=True, fc=LIV, ec="#555555", lw=1.0,
                             zorder=1))
        for d_lag, d_hog in ((h / 2 - hf, h / 2),      # overflans
                             (-h / 2, -h / 2 + hf)):   # underflans
            ax.add_patch(Polygon(_profil(alfa, hoger, d_lag, d_hog, langd),
                                 closed=True, fc=FLANS, ec="#555555",
                                 lw=0.8, zorder=2))

    # -- skivorna ------------------------------------------------------
    ax.add_patch(Polygon(_skivhorn(alfa, fb["skiva_hojd_liv"], l_liv),
                         closed=True, fc=SKIVA, ec="#7a6a3f", lw=1.0,
                         alpha=0.45, zorder=3))
    ax.add_patch(Polygon(_skivhorn(alfa, fb["skiva_hojd_ytter"], l_yt),
                         closed=True, fc="none", ec="#6d5c2f", lw=1.2,
                         ls=(0, (7, 4)), zorder=4))

    # -- fogen: LODRAT -------------------------------------------------
    topp = h / 2 / cos(alfa) + 26
    ax.plot([0, 0], [-topp, topp], color="crimson", lw=2.0,
            ls=(0, (6, 3)), zorder=7)
    ax.text(0, topp + 12, "STÖTFOG (lodrät)", ha="center", fontsize=9.5,
            color="crimson", weight="bold")

    # -- spikarna ------------------------------------------------------
    # Ledad nock har sin EGEN spikbild (skivor bara pa livet, 5.3.7) --
    # den ritas, inte den momentstyva. Bild och siffra ur samma grupp.
    fargar = {"flans": "#111111", "liv": "#b3401f"}
    if res.nocktyp == "ledad" and res.ledad is not None:
        led = res.ledad
        lagen = sorted(set(led.grupp.coords))
        pkt = []
        for x, yc in lagen:
            y = yc + led.e                 # absolut avstand fran fogen
            pkt += [_vrid(x, y, alfa, True), _vrid(x, -y, alfa, False)]
        ax.scatter([p[0] for p in pkt], [p[1] for p in pkt], s=17,
                   c=fargar["liv"], zorder=8, marker="o",
                   label=f"Ledad nock (5.3.7): {2 * led.grupp.n} spik "
                         f"totalt, e = {led.e:.0f} mm")
    else:
        for gr in res.grupper:
            vilken = "flans" if "flans" in gr.namn else "liv"
            pkt = [_vrid(x, y, alfa, y > 0)
                   for x, y in sorted(set(gr.grupp.coords))]
            ax.scatter([p[0] for p in pkt], [p[1] for p in pkt], s=17,
                       c=fargar[vilken], zorder=8, marker="o",
                       label=f"{gr.namn}: {gr.antal} st "
                             f"{gr.forbindare.namn}, {gr.n_snitt} snitt")

    # -- vinkeln -------------------------------------------------------
    lut = cfg["geometri"]["taklutning"]
    for hoger in (False, True):
        u, _ = _riktning(alfa, hoger)
        p = langd * 0.62 * u
        ax.plot([0, p[0]], [0, p[1]], color="#8a5a2b", lw=0.8, ls=":",
                zorder=6)

    # -- matt ----------------------------------------------------------
    # c/c-mattet tas mellan tva spikar i SAMMA kolonn -- efter
    # stotfogsanpassningen borjar kolonnerna pa olika y, sa tva
    # godtyckliga grannvarden kan hora till olika kolonner och ge en
    # linje som inte ar 25 mm lang fast etiketten sager det.
    kolonner = {}
    for gr in res.grupper:
        # bara sida +Y: unionen av bada sidorna har halva delningen
        # mellan grannvarden nar sidorna ar forskjutna
        sida_a = getattr(gr.grupp, "sidor",
                         (gr.grupp.coords[:len(gr.grupp.coords) // 2],))[0]
        for x, y in sida_a:
            if y > 0:
                kolonner.setdefault(round(x, 3), set()).add(y)
    kol = max(kolonner.values(), key=len) if kolonner else set()
    ys = sorted(kol)
    if len(ys) >= 2:
        x_kol = next(x for x, v in kolonner.items() if v == kol)
        p1 = _vrid(h / 2 + 16, ys[0], alfa, True)
        p2 = _vrid(h / 2 + 16, ys[1], alfa, True)
        _mattlinje(ax, p1[0], p1[1], p2[0], p2[1],
                   f"c/c {ys[1] - ys[0]:.0f}", off=10)
    for avst, txt, off in ((l_liv, f"livförstärkning {l_liv:.0f} från fogen",
                            -h / 2 - 70),
                           (l_yt, f"utanpåliggande skiva {l_yt:.0f} från "
                                  f"fogen", -h / 2 - 122)):
        a = _vrid(off, 0, alfa, True)
        b = _vrid(off, avst, alfa, True)
        _mattlinje(ax, a[0], a[1], b[0], b[1], txt, off=-11)

    ax.legend(loc="upper right", bbox_to_anchor=(1.0, -0.02), fontsize=7.5,
              frameon=True, markerscale=1.2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.margins(0.06, 0.10)
    ax.set_title(
        f"Nockförband, {res.nocktyp} nock — {balk.namn}, taklutning "
        f"{lut:.0f}° (nockvinkel {180 - 2 * lut:.0f}°, mått i mm)",
        fontsize=10)
    fig.tight_layout()
    return fig


def _rect(x, y, b, h, fc, alpha=1.0, ec="#555555", ls="-"):
    from matplotlib.patches import Rectangle
    return Rectangle((x, y), b, h, facecolor=fc, edgecolor=ec,
                     alpha=alpha, lw=0.8, linestyle=ls)


def _skivlangd(res, vilken, s):
    """
    Minsta skivlangd langs balken: spikarnas utbredning plus kantavstand
    at bada hall. Skivans langd finns inte i modellen -- den har figuren
    visar alltsa MINIMIMATTET som spikbilden kraver.
    """
    gr = next((g for g in res.grupper if vilken in g.namn), None)
    if gr is None:
        return 200.0
    y_max = max(abs(y) for _, y in gr.grupp.coords)
    # 15d = a3t (belastad ande): samma spegelargument som stotfogen --
    # de andnara spikarnas momentkrafter ar motriktade mellan halvorna,
    # sa minst EN skivande ar belastad i varje momentstyv korning, och
    # i lyftfallet drar N/n mot anden. 10d (a3c) racker alltsa inte.
    # Granskningsfynd 2026-08-19. Galler aven osb/spanskiva (EC5
    # 8.3.1.3(1) lamnar tab. 8.2:s andavstand oforandrade).
    kant = 15 * gr.forbindare.d
    return 2 * (y_max + kant)


def tvarsnitt(res, cfg):
    """
    Tvarsnitt genom balken vid nocken: varfor livforstarkningen spikas i
    LIVET och den utanpaliggande skivan i FLANSARNA.

    Livet ar indraget (b_flans - t_liv)/2 fran flansarnas sidor. Den
    indragningen ar precis vad livforstarkningen fyller; forst darefter
    ligger balksidan plan sa att en utanpaliggande skiva bar mot
    flansarna. En skiva som lades direkt utanpa skulle spanna over ett
    hal och inte na livet alls.
    """
    from matplotlib.patches import Rectangle

    balk = res.balk
    fb = cfg["forband"]
    t = fb["skiva_t"]
    bf, tl, h, hf = balk.b_flans, balk.t_liv, balk.h, balk.h_flans
    indrag = (bf - tl) / 2.0

    fig = Figure(figsize=(5.4, 4.6), dpi=115)
    ax = fig.add_subplot(111)

    # balken sedd i tvarsnitt: bredden vagratt, hojden lodratt
    ax.add_patch(Rectangle((-bf / 2, h / 2 - hf), bf, hf, fc=FLANS,
                           ec="#555555", lw=1.0, zorder=3))
    ax.add_patch(Rectangle((-bf / 2, -h / 2), bf, hf, fc=FLANS,
                           ec="#555555", lw=1.0, zorder=3))
    ax.add_patch(Rectangle((-tl / 2, -h / 2 + hf), tl, h - 2 * hf, fc=LIV,
                           ec="#555555", lw=1.0, zorder=3))

    # livforstarkningen: fyller indragningen, mot LIVET
    for sida in (1, -1):
        ax.add_patch(Rectangle(
            (sida * tl / 2 if sida > 0 else -tl / 2 - t,
             -fb["skiva_hojd_liv"] / 2), t, fb["skiva_hojd_liv"],
            fc=SKIVA, ec="#7a6a3f", lw=1.0, alpha=0.75, zorder=4))
    # utanpaliggande: mot FLANSARNAS sidor
    for sida in (1, -1):
        ax.add_patch(Rectangle(
            (sida * bf / 2 if sida > 0 else -bf / 2 - t,
             -fb["skiva_hojd_ytter"] / 2), t, fb["skiva_hojd_ytter"],
            fc="none", ec="#6d5c2f", lw=1.4, ls=(0, (6, 3)), zorder=5))

    # Spikarna ritas med sina VERKLIGA langder och slas fran VAR SIDA.
    # Flansspiken nar (langd - t) in i flansen; spikarna fran motstaende
    # sidor overlappar dar och far darfor inte sitta mitt for varandra --
    # de forskjuts langs balken (zigzag, handboken s. 284). Langs balken
    # syns inte i det har snittet, sa forskjutningen visas som en liten
    # hojdforskjutning i stallet.
    import material
    sp_f = material.forbindare(fb["forbindare_flans"])
    sp_l = material.forbindare(fb["forbindare_liv"])
    dy = 5.0                      # symbol for forskjutningen langs balken
    for sida in (1, -1):
        # livspiken: genom skiva -> LIV -> skiva (tva skjuvsnitt)
        x1 = sida * (tl / 2 + t)
        x2 = x1 - sida * sp_l.langd
        y = sida * dy
        ax.plot([x1, x2], [y, y], color="#b3401f", lw=1.6, zorder=6,
                solid_capstyle="butt")
        ax.plot([x1, x1], [y - 4, y + 4], color="#b3401f", lw=1.6,
                zorder=6)
        # flansspiken: genom utanpaliggande skiva, in i flansens sidoyta
        for tecken in (1, -1):
            yf = tecken * (h / 2 - hf / 2) + sida * dy
            xf1 = sida * (bf / 2 + t)
            xf2 = xf1 - sida * sp_f.langd
            ax.plot([xf1, xf2], [yf, yf], color="#111111", lw=1.6,
                    zorder=6, solid_capstyle="butt")
            ax.plot([xf1, xf1], [yf - 4, yf + 4], color="#111111", lw=1.6,
                    zorder=6)
    ax.plot([], [], color="#b3401f", lw=1.6,
            label=f"spik ({sp_l.langd:.0f} mm) genom livförstärkning -> "
                  f"LIV -> livförstärkning\n(två skjuvsnitt), från var "
                  f"sida")
    ax.plot([], [], color="#111111", lw=1.6,
            label=f"spik ({sp_f.langd:.0f} mm) genom utanpåliggande "
                  f"skiva -> FLÄNS\n(ett skjuvsnitt), från var sida: "
                  f"{sp_f.langd - t:.0f} mm indrivning i flänsen")
    ax.text(0, h / 2 + 56,
            "Spik från motstående sidor förskjuts längs balken och möts "
            "inte\n(förskjutningen ritad som höjdskillnad här).",
            ha="center", fontsize=7.5, color="#555555")

    _mattlinje(ax, tl / 2, h / 2 + 22, bf / 2, h / 2 + 22,
               f"indrag {indrag:.1f}", off=12)
    _mattlinje(ax, -bf / 2, -h / 2 - 26, bf / 2, -h / 2 - 26,
               f"flänsbredd {bf:.0f}", off=-12)
    _mattlinje(ax, -tl / 2, -h / 2 - 56, tl / 2, -h / 2 - 56,
               f"liv {tl:.0f}", off=-12)

    passar = abs(indrag - t) <= 2.0
    ax.text(0, -h / 2 - 96,
            (f"Livförstärkningen ({t:.0f} mm) fyller indragningen "
             f"({indrag:.1f} mm)."
             if passar else
             f"OBS: livförstärkningen är {t:.0f} mm men indragningen "
             f"{indrag:.1f} mm.\nDen utanpåliggande skivan spänner då över "
             f"en glipa på {indrag - t:.1f} mm."),
            ha="center", fontsize=8.5,
            color="#333333" if passar else "#b30000",
            bbox=dict(fc="#f6f6f6" if passar else "#ffecec",
                      ec="#cccccc" if passar else "#b30000", pad=4))

    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.03), fontsize=7.5,
              frameon=True)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-bf / 2 - t - 60, bf / 2 + t + 60)
    ax.set_ylim(-h / 2 - 120, h / 2 + 82)
    ax.set_title(f"Tvärsnitt vid nocken — {balk.namn} (mått i mm)",
                 fontsize=10.5)
    fig.tight_layout()
    return fig


def takstol(cfg, res):
    """Takstolens geometri med de matt som styr berakningen."""
    g = cfg["geometri"]
    L = g["spannvidd"]
    a = radians(g["taklutning"])
    rise = L / 2 * tan(a)
    L_sp = res.nedbojning.L_sparre

    fig = Figure(figsize=(7.2, 3.6), dpi=115)
    ax = fig.add_subplot(111)

    ax.plot([0, L / 2, L], [0, rise, 0], color="#8a5a2b", lw=7,
            solid_capstyle="round", zorder=3)
    ax.plot([0, L], [0, 0], color="#999999", lw=1.0, ls=":")

    for x in (0, L):
        ax.plot([x - L * 0.02, x + L * 0.02], [-0.06, -0.06],
                color="#333333", lw=2.5)
        ax.plot([x, x - L * 0.02, x + L * 0.02, x],
                [0, -0.06, -0.06, 0], color="#333333", lw=1.2)

    ax.plot(L / 2, rise, marker="o", ms=11, mfc="crimson", mec="black",
            zorder=5)
    ax.text(L / 2, rise + L * 0.035,
            f"nock: {res.nocktyp}\nM = {res.dimensionerande.M:.2f} kNm",
            ha="center", fontsize=8, color="crimson")

    _mattlinje(ax, 0, -L * 0.055, L, -L * 0.055,
               f"spännvidd {L:.2f} m", off=-L * 0.022)
    _mattlinje(ax, L, 0, L, rise, f"{rise:.2f} m", off=L * 0.03,
               vertikal=True)
    ax.annotate(f"{g['taklutning']:.0f}°", (L * 0.12, L * 0.012),
                fontsize=9, color="#8a5a2b")
    ax.text(L * 0.25, rise * 0.55, f"sparre {L_sp:.2f} m", fontsize=8,
            rotation=degrees(a), color="#8a5a2b", ha="center")

    # Utstick y: balkens forlangning UTANFOR upplaget (ETA fig. 2).
    # Ritas som sparrens fortsattning forbi stodet, med matt. Utsticket
    # hojer upplagskapaciteten via delta-a (ekv. 5) -- men dess egen last
    # ingar INTE i ramen, se granskningsanteckningen i ERRATA.
    y_mm = float(cfg.get("upplag", {}).get("overhang_y", 0.0))
    if y_mm > 0:
        y_m = y_mm / 1000.0
        for x0, rikt in ((0.0, -1), (L, 1)):
            dx, dy = rikt * y_m * cos(a), -y_m * sin(a)
            ax.plot([x0, x0 + dx], [0, dy], color="#8a5a2b", lw=7,
                    solid_capstyle="round", zorder=2, alpha=0.55)
        _mattlinje(ax, 0, L * 0.035, -y_m * cos(a), L * 0.035,
                   f"utstick y = {y_mm:.0f} mm", off=L * 0.022)

    bs = res.balksnitt
    xs = bs.s * cos(a) if bs.sparre == "vanster" else L - bs.s * cos(a)
    ys = bs.s * sin(a)
    ax.plot(xs, ys, marker="v", ms=9, mfc="#1f77b4", mec="black", zorder=6)
    # Etiketten laggs UNDER sparren och lite at sidan, annars skriver den
    # over balken.
    ax.annotate(f"värsta snittet {bs.s:.2f} m från takfot\n"
                f"u = {res.varsta_balkkontroll.utnyttjande:.3f}",
                (xs, ys), xytext=(xs + L * 0.10, ys - L * 0.115),
                fontsize=7.5, color="#1f77b4", ha="left",
                arrowprops=dict(arrowstyle="-", color="#1f77b4", lw=0.7),
                bbox=dict(fc="white", ec="#1f77b4", alpha=0.9, pad=2))

    ax.text(L * 0.5, -L * 0.115,
            f"c/c takstolar {g['cc']:.2f} m   |   {res.balk.namn}   |   "
            f"upplag L1 = {cfg.get('upplag', {}).get('L1', 0):.0f} mm",
            ha="center", fontsize=8, color="#444444")

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(-L * 0.09, L * 1.12)
    ax.set_ylim(-L * 0.16, rise + L * 0.13)
    fig.tight_layout()
    return fig
