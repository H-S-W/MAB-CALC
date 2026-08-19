"""
3D-modell av takstolen med nockforbandet -- ersatter de tre 2D-flikarna
med EN modell som gar att vrida, zooma och matta i.

Modulen innehaller INGEN ingenjorslogik och inga materialvarden. All
geometri kommer ur samma kallor som berakningen och 2D-ritningarna:

  - spiklagen ur res.grupper / res.ledad (dar I_p raknas), vridna med
    forband.vrid_till_nock -- SAMMA transform som nockfjadern K_r,
  - sparr- och skivkonturer ur ritning._profil / _skivhorn,
  - skivlangder ur ritning._skivlangd (minimimatt: spikbild + kant).

Delningen ar avsiktlig:

  geometri(res, cfg, detalj)  ->  ren mattdata (dict med prismor, spik,
                                  matt och produktionstabeller). Den
                                  laser testerna pa, och den blir
                                  CSV-exporten for produktion.
  modell(res, cfg, detalj)    ->  plotly-figur byggd ENBART ur
                                  geometri(). Ingen egen geometri.

Koordinatsystem (mm): X langs spannvidden (0 i stotfogen), Y tvars
takstolen (0 i balkens mittplan), Z lodratt (0 dar balkaxeln korsar
fogen). Elevationen (X, Z) ar identisk med 2D-ritningarnas plan.
"""

from math import cos, radians

import material
from forband import vrid_till_nock
from ritning import (FLANS, LIV, MATT, SKIVA, _profil, _skivhorn,
                     _skivlangd)

STOD = "#8f8f8f"


# ---------------------------------------------------------------------------
# Polygon -> prisma (for plotly Mesh3d)
# ---------------------------------------------------------------------------
def _kryss(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _i_triangel(p, a, b, c):
    d1, d2, d3 = _kryss(a, b, p), _kryss(b, c, p), _kryss(c, a, p)
    neg = d1 < -1e-9 or d2 < -1e-9 or d3 < -1e-9
    pos = d1 > 1e-9 or d2 > 1e-9 or d3 > 1e-9
    return not (neg and pos)


def _triangulering(poly):
    """
    Oronklippning av en enkel polygon. Skivkonturen ar INTE konvex
    (underkanten viker upp mot nocken), sa en solfjader fran ett horn
    racker inte -- den skulle lagga trianglar utanfor skivan.
    """
    n = len(poly)
    if sum(_kryss((0, 0), poly[i], poly[(i + 1) % n])
           for i in range(n)) < 0:
        ordning = list(range(n - 1, -1, -1))       # gor polygonen moturs
    else:
        ordning = list(range(n))
    trianglar = []
    vakt = 0
    while len(ordning) > 3 and vakt < 1000:
        vakt += 1
        for k in range(len(ordning)):
            i0 = ordning[k - 1]
            i1 = ordning[k]
            i2 = ordning[(k + 1) % len(ordning)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if _kryss(a, b, c) <= 1e-9:            # konkavt horn
                continue
            if any(_i_triangel(poly[m], a, b, c)
                   for m in ordning if m not in (i0, i1, i2)):
                continue
            trianglar.append((i0, i1, i2))
            ordning.pop(k)
            break
    trianglar.append(tuple(ordning[:3]))
    return trianglar


def _prisma(namn, poly, y0, y1, farg, opacity=1.0):
    """Polygon i (X, Z)-planet utdragen i Y-led till en solid kropp."""
    poly = [(float(p[0]), float(p[1])) for p in poly]
    n = len(poly)
    x = [p[0] for p in poly] * 2
    z = [p[1] for p in poly] * 2
    y = [float(y0)] * n + [float(y1)] * n
    i, j, k = [], [], []
    for a, b, c in _triangulering(poly):           # lock
        i += [a, a + n]
        j += [c, b + n]
        k += [b, c + n]
    for a in range(n):                             # mantelytor
        b = (a + 1) % n
        i += [a, a]
        j += [b, b + n]
        k += [b + n, a + n]
    return dict(namn=namn, x=x, y=y, z=z, i=i, j=j, k=k,
                farg=farg, opacity=opacity, poly=poly, y0=y0, y1=y1)


# ---------------------------------------------------------------------------
# Geometrin -- ren mattdata
# ---------------------------------------------------------------------------
def geometri(res, cfg, detalj=True):
    """
    All 3D-geometri och produktionsdata som ren data. Spiklagen ar
    vrid_till_nock(x, y) av EXAKT de koordinater berakningen raknar
    I_p med -- bild, siffra och produktionstabell ur samma kalla.
    """
    balk = res.balk
    fb = cfg["forband"]
    g = cfg["geometri"]
    s = fb["cc_forbindare"]
    alfa = radians(g["taklutning"])
    c = cos(alfa)
    h, hf, bf, tl = balk.h, balk.h_flans, balk.b_flans, balk.t_liv
    t = fb["skiva_t"]
    L = g["spannvidd"] * 1000.0                    # ramen raknar i m
    overhang = float(cfg.get("upplag", {}).get("overhang_y", 0.0))
    ledad = res.nocktyp == "ledad" and res.ledad is not None

    l_liv = _skivlangd(res, "liv", s) / 2          # langs balkaxeln
    l_yt = _skivlangd(res, "flans", s) / 2
    L1 = float(cfg.get("upplag", {}).get("L1", 45.0))

    # Underkantens punkt pa axelavstandet a fran fogen (hoger sparre):
    # P = a*u + (-h/2)*n med u = (cos, -sin), n = (sin, cos). Ger
    # z_under(x) = -x*tan(alfa) - (h/2)/cos(alfa) -- testlast.
    sin_a = (1 - c * c) ** 0.5
    def _under(a):
        return (a * c - (h / 2) * sin_a, -a * sin_a - (h / 2) * c)
    # Kontaktstrackan L1 (LANGS balken, ETA:ns matt) centreras sa att
    # dess mitt hamnar rakt over upplagets centrumlinje X = L/2
    # (spannvidden ar centrum-centrum). Underkanten ligger fore axeln
    # i X-led, darfor korrektionen +(h/2)*sin(alfa).
    a_c = (L / 2 + (h / 2) * sin_a) / c
    a_ytter = a_c + L1 / 2

    # Sparrlangd langs axeln: hela vagen till upplaget (+ utstick),
    # eller bara nockdetaljen (samma matt som 2D-ritningen).
    if detalj:
        alla_y = [abs(y) for gr in res.grupper for _, y in gr.grupp.coords]
        y_max = max(alla_y) if alla_y else 100.0
        langd = max(y_max + 3 * s, l_yt + 25)
    else:
        # Hela vagen over upplaget: utsticket y raknas fran stodets
        # YTTERKANT (ETA fig. 2 -- det ar det y som gar in i delta_a,
        # ekv. 5), inte fran centrumlinjen. Granskningsfynd 2026-08-19:
        # den aldre langden (L/2)/cos + overhang slutade fore stodet.
        langd = a_ytter + overhang

    prismor = []

    # -- sparrarna: liv + tva flansar per sida, kapade i fogplanet ------
    for hoger in (False, True):
        sida = "höger" if hoger else "vänster"
        # Balken lite genomskinlig sa spikdjup och skivor syns i 3D
        prismor.append(_prisma(
            f"Liv ({sida})", _profil(alfa, hoger, -h / 2 + hf, h / 2 - hf,
                                     langd), -tl / 2, tl / 2, LIV, 0.62))
        for d_lag, d_hog, var in ((h / 2 - hf, h / 2, "Överfläns"),
                                  (-h / 2, -h / 2 + hf, "Underfläns")):
            prismor.append(_prisma(
                f"{var} ({sida})",
                _profil(alfa, hoger, d_lag, d_hog, langd),
                -bf / 2, bf / 2, FLANS, 0.62))

    # -- skivorna: pa BADA sidor. Ledad nock har bara livskivor ---------
    # Skivorna LAGT genomskinliga sa spikbilden syns igenom -- deras
    # utstrackning bars i stallet av skarpa KONTURLINJER pa ytterytan
    # (Mesh3d saknar kanter; hog opacitet gjorde framvyn till en enda
    # plywoodklump).
    skivsatser = [("Livforstarkning", fb["skiva_hojd_liv"], l_liv,
                   tl / 2, SKIVA, 0.50)]
    if not ledad:
        skivsatser.append(("Utanpaliggande skiva", fb["skiva_hojd_ytter"],
                           l_yt, bf / 2, SKIVA, 0.35))
    skivor = []
    konturer = []
    for namn, hojd, halvlangd, inre, farg, op in skivsatser:
        horn = [(float(p[0]), float(p[1]))
                for p in _skivhorn(alfa, hojd, halvlangd)]
        xs = [p[0] for p in horn]
        zs = [p[1] for p in horn]
        y_sidor = []
        for tecken in (1, -1):
            y0, y1 = tecken * inre, tecken * (inre + t)
            y_sidor.append((min(y0, y1), max(y0, y1)))
            prismor.append(_prisma(f"{namn} (y {'+' if tecken > 0 else '-'})",
                                   horn, y0, y1, farg, op))
            yttre = tecken * (inre + t)
            konturer.append(dict(
                punkter=[(px, yttre, pz) for px, pz in horn + [horn[0]]]))
        skivor.append(dict(namn=namn, antal=2, tjocklek=t, hojd=hojd,
                           halvlangd_langs_balk=halvlangd,
                           bbox_langd=max(xs) - min(xs),
                           bbox_hojd=max(zs) - min(zs),
                           horn=horn, y_sidor=y_sidor))

    texter = []
    # -- spikarna: verkliga langder, fran bada sidor --------------------
    # Berakningens coords ar dubblerade (*2 = en spikbild per sida), sa
    # de UNIKA lagena ritas en gang per sida och antalen stammer med
    # gr.antal. Spik fran motstaende sidor far inte sitta mitt for
    # varandra i verkligheten -- forskjutningen langs balken ar ett
    # UTFORANDEKRAV som modellen inte styr; den redovisas som text.
    spikgrupper = []
    spiktabell = []
    spiklinjer = []
    linjer = []                        # kritlinjer i modellen
    rutnat_data = {}                   # per skiva: rader/kolonner for rutnatet
    fs = float(fb.get("sidoforskjutning", 0.0)) * s
    # Varje SIDA har sin egen spikbild (grupp.sidor): sida -Y ar
    # forskjuten langs balken sa att spik fran motstaende sidor inte
    # kolliderar -- placeringen ar den verkliga och berakningen raknar
    # pa exakt dessa lagen.
    def _sidolagen(grupp, e=0.0):
        # fallback for grupper utan sidor-attribut: coords ar alltid
        # A + B i den ordningen (aldre *2-bild = tva identiska halfter)
        n2 = len(grupp.coords) // 2
        a, b = getattr(grupp, "sidor",
                       (grupp.coords[:n2], grupp.coords[n2:]))
        if e:                              # ledad: relativt tyngdpunkten
            a = [(x, tecken * (y + e)) for x, y in a for tecken in (1, -1)]
            b = [(x, tecken * (y + e)) for x, y in b for tecken in (1, -1)]
        return (sorted(set(a)), sorted(set(b)))
    if ledad:
        led = res.ledad
        sp = material.forbindare(fb["forbindare_liv"])
        satser = [("Ledad nock (5.3.7)", "Livforstarkning",
                   _sidolagen(led.grupp, led.e), tl / 2 + t, sp,
                   "#b3401f")]
    else:
        satser = []
        for gr in res.grupper:
            i_flans = "flans" in gr.namn
            satser.append((
                gr.namn,
                "Utanpaliggande skiva" if i_flans else "Livforstarkning",
                _sidolagen(gr.grupp),
                (bf / 2 if i_flans else tl / 2) + t,
                gr.forbindare,
                "#111111" if i_flans else "#b3401f"))
    for namn, skiva, sidolagen, y_in, sp, farg in satser:
        segment = []
        for tecken, lagen in ((1, sidolagen[0]), (-1, sidolagen[1])):
            for x, y in lagen:
                px, pz = vrid_till_nock(x, y, alfa)
                y_start = tecken * y_in
                y_slut = y_start - tecken * sp.langd
                segment.append(((px, y_start, pz), (px, y_slut, pz)))
                spiktabell.append(dict(
                    skiva=skiva, grupp=namn,
                    sida="+Y" if tecken > 0 else "-Y",
                    x_mm=round(px, 1), z_mm=round(pz, 1),
                    spik=sp.namn, langd_mm=sp.langd))
        spikgrupper.append(dict(
            namn=namn, farg=farg, segment=segment,
            etikett=f"{namn}: {len(segment)} st {sp.namn}"))
        # SPIKLINJER -- produktionens sprak: kolonnerna ligger pa fasta
        # vinkelrata avstand fran balkaxeln (= skivans mittlinje), sa
        # varje kolonn ar en KRITLINJE parallell med skivans over-/
        # underkant. Utsattning: mat vinkelratt fran overkanten, snapp
        # linjen, mark forsta spiken fran fogens mittlinje (matt LANGS
        # linjen), stega delningen. Sidorna skiljer bara i forsta-
        # avstandet (sidoforskjutningen); halvorna ar spegelvanda.
        sk_hojd = next(s2["hojd"] for s2 in skivor if s2["namn"] == skiva)
        for tecken, lagen in ((1, sidolagen[0]), (-1, sidolagen[1])):
            per_x = {}
            for x, y in lagen:
                if y > 0:
                    per_x.setdefault(round(x, 3), []).append(y)
            # tvarlinje_nr raknas fran REFERENSLINJEN (0 = linjen genom
            # flansvinkeln); negativa nummer ligger narmare fogen
            from math import tan as _tan2
            if fb.get("rutnat_ankare", "") == "flansvinkel":
                ref_y = (h / 2) * _tan2(alfa)
            else:
                ref_y = float(fb.get("rutnat_bas", 0.5)) * s
            sidoskift = 0.0 if tecken > 0 else fs
            for x, ys in sorted(per_x.items(), reverse=True):
                ys = sorted(ys)
                spiklinjer.append(dict(
                    skiva=skiva, grupp=namn,
                    sida="+Y" if tecken > 0 else "-Y",
                    fran_overkant_mm=round(sk_hojd / 2 - x, 1),
                    forsta_fran_fog_mm=round(ys[0], 1),
                    tvarlinje_nr=int(round((ys[0] - sidoskift - ref_y)
                                           / s)),
                    delning_mm=round(ys[1] - ys[0], 1)
                    if len(ys) > 1 else None,
                    antal_per_halva=len(ys)))
                if tecken > 0:
                    rd = rutnat_data.setdefault(
                        skiva, dict(ys=set(), xs=set(),
                                    yta=abs(y_in) + 0.5))
                    rd["ys"].update(ys)
                    rd["xs"].add(x)
                if tecken > 0:
                    # linjen i modellen: genom raderna, bada halvorna.
                    # UNDERFLANSENS kritlinje ritas HELDRAGEN och dras
                    # anda fram till fogen: de tva halvornas linjer
                    # mots da exakt i vinkeln mellan undre flansarna
                    # (anvandarbeslut 2026-08-19) -- det ar rutnatets
                    # egen referenslinje. Ovriga linjer finstreckas.
                    # Avstandsetiketterna ar dolda; vardena star i
                    # spiklinjetabellen.
                    y_yta = abs(y_in) - t + 0.5    # skivans ytteryta
                    for halva in (1, -1):
                        a = vrid_till_nock(x, halva * max(ys[0] - 30,
                                                          6.0), alfa)
                        b = vrid_till_nock(x, halva * (ys[-1] + 30), alfa)
                        linjer.append(dict(
                            a=(a[0], y_yta + t, a[1]),
                            b=(b[0], y_yta + t, b[1]), stil="streck"))

    # Tvarlinjerna: rutnatets andra riktning (sida +Y:s raster; sida -Y
    # ligger sidoforskjutningen langre fran fogen). Ritas over spik-
    # zonen sa rutnatet gar att kopiera direkt fran modellen.
    from math import tan as _tan
    for namn_sk, rd in rutnat_data.items():
        x_lo, x_hi = min(rd["xs"]) - 15, max(rd["xs"]) + 15
        for yk in sorted(rd["ys"]):
            for halva in (1, -1):
                a = vrid_till_nock(x_lo, halva * yk, alfa)
                b = vrid_till_nock(x_hi, halva * yk, alfa)
                linjer.append(dict(a=(a[0], rd["yta"], a[1]),
                                   b=(b[0], rd["yta"], b[1]),
                                   stil="streck"))
    # Den HELDRAGNA referenslinjen (anvandarbeslut 2026-08-19, tredje
    # forsoket -- nu ratt): den tvarlinje som TRAFFAR VINKELN MELLAN
    # UNDRE FLANSARNA. Vinkelspetsen ligger (h/2)*tan(alfa) fran fogen
    # langs balkaxeln, sa det ar rasterlinjen narmast det avstandet.
    # Den dras fran vinkelspetsen (x = -h/2) upp genom HELA rutnatet
    # till ytterskivans overkantszon -- en linje per halva.
    alla_yk = sorted({yk for rd in rutnat_data.values()
                      for yk in rd["ys"]})
    if alla_yk:
        y_v = (h / 2) * _tan(alfa) if alfa > 1e-6 else alla_yk[0]
        hel_yk = min(alla_yk, key=lambda yk: abs(yk - y_v))
        x_topp = max(max(rd["xs"]) for rd in rutnat_data.values()) + 15
        yta_max = max(rd["yta"] for rd in rutnat_data.values())
        for halva in (1, -1):
            a = vrid_till_nock(-h / 2, halva * hel_yk, alfa)
            b = vrid_till_nock(x_topp, halva * hel_yk, alfa)
            linjer.append(dict(a=(a[0], yta_max, a[1]),
                               b=(b[0], yta_max, b[1]), stil="hel"))

    # -- upplag och matt -------------------------------------------------
    matt = []
    hjalplinjer = []                   # utdragslinjer (extension lines)
    if detalj:
        # c/c mellan tva spikar i SAMMA kolonn (samma regel som 2D:n)
        kolonner = {}
        grupper = ([res.ledad.grupp] if ledad
                   else [gr.grupp for gr in res.grupper])
        e = res.ledad.e if ledad else 0.0
        for grupp in grupper:
            # bara sida +Y -- sidounionen har halva delningen
            sida_a = getattr(grupp, "sidor",
                             (grupp.coords[:len(grupp.coords) // 2],))[0]
            for x, y in sida_a:
                if y + e > 0:
                    kolonner.setdefault(round(x, 3), set()).add(y + e)
        kol = max(kolonner.values(), key=len) if kolonner else set()
        ys = sorted(kol)
        # ALLA matt laggs i ett plan framfor modellen (y_ut) -- i
        # framvyn (kamera langs -Y) ligger de da fritt framfor skivorna
        # och skyms inte av balken.
        y_ut = max(ys2[1] for ys2 in
                   (sk["y_sidor"][0] for sk in skivor)) + 30
        if len(ys) >= 2:
            x_kol = next(x for x, v in kolonner.items() if v == kol)
            p1 = vrid_till_nock(x_kol, ys[0], alfa)
            p2 = vrid_till_nock(x_kol, ys[1], alfa)
            matt.append(dict(a=(p1[0], y_ut, p1[1]), b=(p2[0], y_ut, p2[1]),
                             text=f"c/c {ys[1] - ys[0]:.0f}",
                             kategori="spik"))
        # KANTMATT (anvandarbeslut 2026-08-19, ersatter hornkoordinater
        # som blev oanvandbara): vanster halvas kanter mattsatts --
        # overkant (nock -> ytterhorn), ande och underkant (ytterhorn ->
        # mittdal) -- plus urtagets djup vid mittdalen. Hoger halva ar
        # spegelvand. Kapa ravan efter bbox-mattet, mark kantlangderna,
        # klart. _skivhorn-ordningen ar [v_top, nocktopp, h_top, h_bot,
        # mittdal, v_bot].
        # Mattlinjerna projiceras forbi SKIVORNAS horn (inte sparrens --
        # det knuffade undre kantens matt langt fran detaljen) och
        # staplas enligt ritningskonvention: kortaste mattet innerst.
        # Livforstarkningens kanter ar kortare an ytterskivans, sa livet
        # far inre nivan (34) och ytterskivan yttre (72) -- samma
        # niva-par for alla kanter (anvandarbeslut 2026-08-19).
        # Referensen ar MOTSVARANDE kant pa ytterskivan (samma index i
        # _skivhorn-ordningen), inte skivans alla horn: den speglade
        # sidans horn ligger langre ut langs underkantens normal och
        # knuffade ivag 230-mattet. ANDEN refererar dessutom balkens
        # horn -- sparren sticker langre an skivorna langs axeln, och
        # mattet ska ligga utanfor balkkanten.
        ref_sk = skivor[-1]["horn"]        # ytterskivan omsluter livets
        alla_pr = [pt for pr in prismor for pt in pr["poly"]]
        for sk in skivor:
            v_top, topp, _, _, dal, v_bot = sk["horn"]
            rv_top, rtopp, _, _, rdal, rv_bot = ref_sk
            y_niva = sk["y_sidor"][0][1] + 8
            mitt_x = sum(px for px, _ in sk["horn"]) / 6
            mitt_z = sum(pz for _, pz in sk["horn"]) / 6
            marginal = (72 if sk["namn"] == "Utanpaliggande skiva"
                        else 34)
            kanter = (((topp, v_top), (rtopp, rv_top), False),
                      ((v_top, v_bot), (rv_top, rv_bot), True),
                      ((v_bot, dal), (rv_bot, rdal), False))
            for (p1, p2), (q1, q2), ande in kanter:
                dx, dz = p2[0] - p1[0], p2[1] - p1[1]
                langd = (dx * dx + dz * dz) ** 0.5
                nx, nz = -dz / langd, dx / langd     # kantens normal
                mx, mz = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                if nx * (mx - mitt_x) + nz * (mz - mitt_z) < 0:
                    nx, nz = -nx, -nz                # utat fran skivan
                ytterst = max(q1[0] * nx + q1[1] * nz,
                              q2[0] * nx + q2[1] * nz)
                if ande:
                    ytterst = max(ytterst, max(hx * nx + hz * nz
                                               for hx, hz in alla_pr))
                for p in (p1, p2):
                    off = ytterst - (p[0] * nx + p[1] * nz) + marginal
                    hjalplinjer.append(dict(
                        a=(p[0] + nx * 6, y_niva, p[1] + nz * 6),
                        b=(p[0] + nx * (off + 9), y_niva,
                           p[1] + nz * (off + 9))))
                o1 = ytterst - (p1[0] * nx + p1[1] * nz) + marginal
                o2 = ytterst - (p2[0] * nx + p2[1] * nz) + marginal
                matt.append(dict(
                    a=(p1[0] + nx * o1, y_niva, p1[1] + nz * o1),
                    b=(p2[0] + nx * o2, y_niva, p2[1] + nz * o2),
                    text=f"{langd:.0f}", kategori="skiva"))
            # urtagsmattet vid mittdalen utgick 2026-08-19 --
            # tolkningen av skissen var osaker; kantlangderna racker
        texter.append(dict(p=(0, y_ut, h / 2 / c + 60),
                           text="STÖTFOG (lodrät)", farg="crimson"))
    else:
        # Upplagsklossens overyta FOLJER balkens lutande underkant over
        # kontaktstrackan L1 -- en horisontell overyta kan aldrig ligga
        # an mot en lutande underkant (granskningsfynd 2026-08-19:
        # sparren svavade 35 mm over stodet). I verkligheten ordnas
        # anliggningen med kilar/klack; modellen visar kontaktytan.
        p1, p2 = _under(a_c - L1 / 2), _under(a_c + L1 / 2)
        zb = min(p1[1], p2[1]) - 70
        for tecken in (-1, 1):
            prismor.append(_prisma(
                f"Upplag ({'vänster' if tecken < 0 else 'höger'})",
                [(tecken * p1[0], p1[1]), (tecken * p2[0], p2[1]),
                 (tecken * p2[0], zb), (tecken * p1[0], zb)],
                -bf / 2, bf / 2, STOD))
        y_fram = bf / 2 + 40                   # framfor balken
        matt.append(dict(a=(-L / 2, y_fram, zb - 90),
                         b=(L / 2, y_fram, zb - 90),
                         text=f"spännvidd {L:.0f} (centrum-centrum)"))
        # Totalhojden: VERTIKALT fran upplagsnivan (balkens underkant
        # vid stodcentrum -- dar takstolen vilar) till nockens topp.
        # "over axeln"-mattet var oanvandbart pa bygget (anvandarbeslut
        # 2026-08-19).
        z_stod = _under(a_c)[1]
        z_topp = (h / 2) / c
        matt.append(dict(a=(0, y_fram, z_stod), b=(0, y_fram, z_topp),
                         text=f"upplag -> nock {z_topp - z_stod:.0f} "
                              f"(vertikalt)"))
        matt.append(dict(a=(_under(a_c)[0], y_fram, z_stod),
                         b=(0, y_fram, z_stod),
                         text="upplagsnivå"))
        lut_z = -(L / 4) * sin_a / c + h
        texter.append(dict(
            p=(L / 4, y_fram, lut_z),
            text=f"taklutning {g['taklutning']:.0f} grader",
            farg=MATT))
        if overhang > 0:
            # fran stodets YTTERKANT till balkanden, langs underkanten
            pa, pb = _under(a_ytter), _under(a_ytter + overhang)
            matt.append(dict(a=(pa[0], y_fram, pa[1] - 55),
                             b=(pb[0], y_fram, pb[1] - 55),
                             text=f"utstick y {overhang:.0f} (från "
                                  f"stödets ytterkant)"))

    titel = (f"{balk.namn}, taklutning {g['taklutning']:.0f} grader — "
             f"{'nockdetalj' if detalj else 'hela takstolen'}, "
             f"{res.nocktyp} nock (mått i mm)")
    return dict(prismor=prismor, spikgrupper=spikgrupper, skivor=skivor,
                spiktabell=spiktabell, spiklinjer=spiklinjer,
                linjer=linjer, matt=matt, texter=texter,
                konturer=konturer, hjalplinjer=hjalplinjer, titel=titel)


# ---------------------------------------------------------------------------
# Plotly-figuren -- byggd enbart ur geometri()
# ---------------------------------------------------------------------------
# Plotlys scrollzoom har ingen kanslighetsinstallning, sa den dampas
# har: wheel-handelsen fangas i capture-fasen, stoppas, och skickas om
# med deltaY/10 -- ett scrollsteg motsvarar en tiondel av plotlys
# standardsteg. Markoren __lugn slapper igenom det omskickade eventet.
# {plot_id} ersatts av plotly vid exporten (to_html/post_script).
# I ORTOGRAFISKT lage ar plotlys zoom ett FAST steg (faktor 1,1) per
# wheel-handelse -- deltats storlek ignoreras (plotly.js: "s = deltaX >
# deltaY ? 1.1 : 0.909..."; zoomen gors via glplot.setAspectratio).
# Deltadampning hjalper alltsa bara i perspektiv; i orto tar filtret
# over helt och tar tiondelssteget 1,1^(1/10) med samma mekanism.
LUGN_ZOOM = """
var gd = document.getElementById('{plot_id}');
var LUGN = 10;

// All zoom gar genom EN vag: steg i "hjulklick" (positivt = ut).
// Perspektiv: dampat wheel-event till plotly. Ortografiskt: plotlys
// zoom ar ett FAST steg per event oavsett delta, sa dar skalas
// aspectratio direkt med tiondelssteg -- samma mekanism som plotly.
function zooma(steg, cx, cy, dampa) {
  // dampa=false: pinch ar en direkt handrorelse och ska folja
  // fingrarna 1:1 -- dampningen galler bara hjul och knappar
  var div = dampa === false ? 1 : LUGN;
  try {
    var scen = gd._fullLayout.scene && gd._fullLayout.scene._scene;
    if (scen && scen.camera && scen.camera._ortho) {
      var s = Math.pow(1.1, steg / div);
      var l = scen.glplot.getAspectratio();
      scen.glplot.setAspectratio({ x: s * l.x, y: s * l.y, z: s * l.z });
      return;
    }
  } catch (fel) { /* fall vidare till wheel-vagen */ }
  var mal = gd.querySelector('canvas') || gd;
  var r = mal.getBoundingClientRect();
  var ev = new WheelEvent('wheel', {
    deltaY: 100 * steg / div, deltaX: 0,
    clientX: cx != null ? cx : r.left + r.width / 2,
    clientY: cy != null ? cy : r.top + r.height / 2,
    bubbles: true, cancelable: true, view: window });
  ev.__lugn = true;
  mal.dispatchEvent(ev);
}

// Mushjul: fanga, dampa, skicka genom zooma()
gd.addEventListener('wheel', function (e) {
  if (e.__lugn) { return; }
  e.preventDefault();
  e.stopImmediatePropagation();
  zooma(e.deltaY / 100, e.clientX, e.clientY);
}, { capture: true, passive: false });

// Pinch pa touchskarm: plotlys 3D-lage saknar den helt. Tva fingrar
// foljs via pointer events och avstandsandringen blir zoomsteg.
var pekare = new Map();
var pinchAvstand = null;
gd.addEventListener('pointerdown', function (e) {
  if (e.pointerType === 'touch') {
    pekare.set(e.pointerId, [e.clientX, e.clientY]);
    pinchAvstand = null;
  }
});
gd.addEventListener('pointermove', function (e) {
  if (e.pointerType !== 'touch' || !pekare.has(e.pointerId)) { return; }
  pekare.set(e.pointerId, [e.clientX, e.clientY]);
  if (pekare.size !== 2) { return; }
  var pts = Array.from(pekare.values());
  var d = Math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]);
  if (pinchAvstand !== null && d > 0) {
    zooma((pinchAvstand - d) / 25,
          (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2,
          false);
    e.preventDefault();
  }
  pinchAvstand = d;
}, { passive: false });
['pointerup', 'pointercancel', 'pointerleave'].forEach(function (typ) {
  gd.addEventListener(typ, function (e) {
    pekare.delete(e.pointerId);
    pinchAvstand = null;
  });
});

// +/- -knappar (touchvanliga, hall inne for kontinuerlig zoom)
var rad = document.createElement('div');
rad.style.cssText = 'position:absolute;right:12px;bottom:16px;' +
  'display:flex;flex-direction:column;gap:8px;z-index:1000;';
[['+', -5], ['\u2212', 5]].forEach(function (par) {
  var b = document.createElement('button');
  b.textContent = par[0];
  b.setAttribute('aria-label', par[1] < 0 ? 'Zooma in' : 'Zooma ut');
  b.style.cssText = 'width:44px;height:44px;border-radius:50%;' +
    'border:1px solid #999;background:rgba(255,255,255,.88);' +
    'font-size:24px;line-height:1;cursor:pointer;' +
    'touch-action:manipulation;user-select:none;color:#333;';
  var timer = null;
  function starta(e) {
    e.preventDefault();
    zooma(par[1]);
    timer = setInterval(function () { zooma(par[1]); }, 120);
  }
  function stoppa() { if (timer) { clearInterval(timer); timer = null; } }
  b.addEventListener('pointerdown', starta);
  ['pointerup', 'pointerleave', 'pointercancel']
    .forEach(function (typ) { b.addEventListener(typ, stoppa); });
  rad.appendChild(b);
});
gd.style.position = 'relative';
gd.appendChild(rad);
"""


def som_html(fig, plotlyjs=True):
    """
    Figuren som HTML med dampat scrollzoom. `plotlyjs`: True baddar in
    hela plotly.js (fristaende fil), en URL-strang laddar den darifran
    (appen pekar pa /app/static/plotly.min.js -- lokalt, inget CDN).
    """
    return fig.to_html(include_plotlyjs=plotlyjs, full_html=True,
                       post_script=LUGN_ZOOM,
                       # ingen modebar: den lade sig over vyknapparna
                       # pa smala skarmar
                       config={"displayModeBar": False},
                       default_height="560px")


def _vy(eye, orto, up=None):
    """relayout-argument for en vyknapp (platta nycklar kravs)."""
    return {"scene.camera.eye": eye,
            "scene.camera.up": up or dict(x=0, y=0, z=1),
            "scene.camera.projection.type":
                "orthographic" if orto else "perspective"}


def modell(res, cfg, detalj=True, textstorlek=11,
           visa_spikmatt=True, visa_skivmatt=True):
    """
    Plotly-figuren. `textstorlek` galler mattexterna (appen har en
    slider). `visa_spikmatt`/`visa_skivmatt` tander/slacker spik-
    monstrets matt (rutnat, c/c, linjeavstand) respektive skivornas
    kantmatt med utdragslinjer -- tva knappar i appen. Vyknapparna
    (iso/fram/sida/topp/bak) ligger i figuren sjalv sa de foljer med
    aven i exporterad HTML; fram/sida/topp ar ORTOGRAFISKA -- dar
    lases matten som pa en planritning.
    """
    import plotly.graph_objects as go

    geo = geometri(res, cfg, detalj)

    def synlig(post):
        kat = post.get("kategori")
        if kat == "spik":
            return visa_spikmatt
        if kat == "skiva":
            return visa_skivmatt
        return True
    geo["matt"] = [m for m in geo["matt"] if synlig(m)]
    geo["texter"] = [t2 for t2 in geo["texter"] if synlig(t2)]
    if not visa_spikmatt:
        geo["linjer"] = []
    if not visa_skivmatt:
        geo["hjalplinjer"] = []
    fig = go.Figure()
    for pr in geo["prismor"]:
        fig.add_trace(go.Mesh3d(
            x=pr["x"], y=pr["y"], z=pr["z"],
            i=pr["i"], j=pr["j"], k=pr["k"],
            color=pr["farg"], opacity=pr["opacity"], flatshading=True,
            # Hog ambient: i de ortografiska vyerna (Fram/Sida) pekar
            # manga ytnormaler bort fran ljuset och diffust ljus gor
            # dem morka -- ambient lyser lika at alla hall.
            lighting=dict(ambient=0.88, diffuse=0.25, specular=0.04),
            lightposition=dict(x=20000, y=60000, z=50000),
            name=pr["namn"], hoverinfo="name", showlegend=False))
    for kt in geo.get("konturer", []):
        fig.add_trace(go.Scatter3d(
            x=[p[0] for p in kt["punkter"]],
            y=[p[1] for p in kt["punkter"]],
            z=[p[2] for p in kt["punkter"]], mode="lines",
            line=dict(color="#6d5c2f", width=3),
            showlegend=False, hoverinfo="skip"))
    for grupp in geo["spikgrupper"]:
        x, y, z = [], [], []
        for (a, b) in grupp["segment"]:
            x += [a[0], b[0], None]
            y += [a[1], b[1], None]
            z += [a[2], b[2], None]
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z, mode="lines",
            line=dict(color=grupp["farg"], width=6),
            name=grupp["etikett"],
            hovertemplate="x %{x:.0f}, y %{y:.0f}, z %{z:.0f} mm"))
        # spikhuvuden: en markering vid indrivningssidan gor bade
        # riktningen och antalet lasbara
        fig.add_trace(go.Scatter3d(
            x=[a[0] for a, _ in grupp["segment"]],
            y=[a[1] for a, _ in grupp["segment"]],
            z=[a[2] for a, _ in grupp["segment"]], mode="markers",
            marker=dict(size=3.4, color=grupp["farg"]),
            showlegend=False,
            hovertemplate="spikhuvud: x %{x:.0f}, y %{y:.0f}, "
                          "z %{z:.0f} mm"))
    mx, my, mz, tx, ty, tz, txt = [], [], [], [], [], [], []
    for m in geo["matt"]:
        a, b = m["a"], m["b"]
        mx += [a[0], b[0], None]
        my += [a[1], b[1], None]
        mz += [a[2], b[2], None]
        tx.append((a[0] + b[0]) / 2)
        ty.append((a[1] + b[1]) / 2)
        tz.append((a[2] + b[2]) / 2)
        txt.append(m["text"])
    for te in geo["texter"]:
        tx.append(te["p"][0])
        ty.append(te["p"][1])
        tz.append(te["p"][2])
        txt.append(te["text"])
    if geo.get("linjer"):
        # Plotlys 3D-linjer har bara grova namngivna monster, sa den
        # fina streckningen byggs for hand: 2 mm streck, 3 mm mellanrum.
        def _finstreck(a, b, streck=2.0, mellanrum=3.0):
            dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            L = (dx * dx + dy * dy + dz * dz) ** 0.5
            if L < 1e-9:
                return [], [], []
            ux, uy, uz = dx / L, dy / L, dz / L
            xs, ys, zs = [], [], []
            pos = 0.0
            while pos < L:
                slut = min(pos + streck, L)
                xs += [a[0] + ux * pos, a[0] + ux * slut, None]
                ys += [a[1] + uy * pos, a[1] + uy * slut, None]
                zs += [a[2] + uz * pos, a[2] + uz * slut, None]
                pos += streck + mellanrum
            return xs, ys, zs

        for hel in (False, True):
            lx, ly, lz = [], [], []
            for ln in geo["linjer"]:
                if (ln.get("stil") == "hel") != hel:
                    continue
                if hel:
                    lx += [ln["a"][0], ln["b"][0], None]
                    ly += [ln["a"][1], ln["b"][1], None]
                    lz += [ln["a"][2], ln["b"][2], None]
                else:
                    dx, dy, dz = _finstreck(ln["a"], ln["b"])
                    lx += dx
                    ly += dy
                    lz += dz
            if not lx:
                continue
            # mittlinjen: samma stil som rutnatet men HELDRAGEN
            fig.add_trace(go.Scatter3d(
                x=lx, y=ly, z=lz, mode="lines",
                line=dict(color=MATT, width=2 if hel else 1.2),
                showlegend=False, hoverinfo="skip",
                opacity=0.85 if hel else 0.5))
    if geo.get("hjalplinjer"):
        hx, hy, hz = [], [], []
        for hl in geo["hjalplinjer"]:
            hx += [hl["a"][0], hl["b"][0], None]
            hy += [hl["a"][1], hl["b"][1], None]
            hz += [hl["a"][2], hl["b"][2], None]
        fig.add_trace(go.Scatter3d(
            x=hx, y=hy, z=hz, mode="lines",
            line=dict(color=MATT, width=1), showlegend=False,
            hoverinfo="skip", opacity=0.7))
    if mx:
        fig.add_trace(go.Scatter3d(
            x=mx, y=my, z=mz, mode="lines",
            line=dict(color=MATT, width=2), name="matt",
            showlegend=False, hoverinfo="skip"))
    if tx:
        fig.add_trace(go.Scatter3d(
            x=tx, y=ty, z=tz, mode="text", text=txt,
            textfont=dict(size=textstorlek, color="#333333"),
            showlegend=False, hoverinfo="skip"))
    iso = (dict(x=0.9, y=1.5, z=0.55) if detalj
           else dict(x=0.55, y=1.9, z=0.7))
    kamera = dict(eye=iso)
    vyer = [("Iso", _vy(iso, orto=False)),
            ("Fram", _vy(dict(x=0, y=2.2, z=0), orto=True)),
            ("Sida", _vy(dict(x=2.2, y=0, z=0), orto=True)),
            ("Topp", _vy(dict(x=0, y=0, z=2.2), orto=True,
                         up=dict(x=0, y=1, z=0))),
            ("Bak", _vy(dict(x=0, y=-2.2, z=0), orto=True))]
    # Ingen figurtitel och ingen plotly-modebar: pa mobil krockade
    # bada med vyknapparna (anvandarbeslut 2026-08-19). Balk/lutning
    # framgar av appens ovriga redovisning; titeln finns kvar i
    # geo["titel"] for den som exporterar.
    fig.update_layout(
        updatemenus=[dict(
            type="buttons", direction="right", showactive=True,
            x=0.0, xanchor="left", y=1.0, yanchor="bottom",
            pad=dict(r=2, t=2), font=dict(size=11),
            buttons=[dict(label=namn, method="relayout", args=[arg])
                     for namn, arg in vyer])],
        scene=dict(
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            zaxis=dict(visible=False), aspectmode="data", camera=kamera,
            bgcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", yanchor="top", y=-0.02,
                    font=dict(size=11)),
        margin=dict(l=0, r=0, t=34, b=0), height=560)
    return fig
