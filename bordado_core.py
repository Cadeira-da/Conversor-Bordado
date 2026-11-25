# -*- coding: utf-8 -*-
"""
Núcleo do Conversor de Bordado: imagem -> pontos -> arquivo .pes (Brother)
e leitura/análise de arquivos .pes existentes.

Unidades internas: 0,1 mm (unidade nativa do formato PEC).
"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------------------
# Paleta PEC (índices 1..64 usados pelas máquinas Brother)
# ---------------------------------------------------------------------------
PEC_PALETTE = [
    None,
    ((0x1a, 0x0a, 0x94), "Azul Prússia"), ((0x0f, 0x75, 0xff), "Azul"),
    ((0x00, 0x93, 0x4c), "Verde Azulado"), ((0xba, 0xbd, 0xfe), "Azul Centáurea"),
    ((0xec, 0x00, 0x00), "Vermelho"), ((0xe4, 0x99, 0x5a), "Marrom Avermelhado"),
    ((0xcc, 0x48, 0xab), "Magenta"), ((0xfd, 0xc4, 0xfa), "Lilás Claro"),
    ((0xdd, 0x84, 0xcd), "Lilás"), ((0x6b, 0xd3, 0x8a), "Verde Menta"),
    ((0xe4, 0xa9, 0x45), "Dourado Escuro"), ((0xff, 0xbd, 0x42), "Laranja"),
    ((0xff, 0xe6, 0x00), "Amarelo"), ((0x6c, 0xd9, 0x00), "Verde Limão"),
    ((0xc1, 0xa9, 0x41), "Latão"), ((0xb5, 0xad, 0x97), "Prata"),
    ((0xba, 0x9c, 0x5f), "Marrom Ruço"), ((0xfa, 0xf5, 0x9e), "Creme"),
    ((0x80, 0x80, 0x80), "Estanho"), ((0x00, 0x00, 0x00), "Preto"),
    ((0x00, 0x1c, 0xdf), "Ultramarino"), ((0xdf, 0x00, 0xb8), "Roxo Real"),
    ((0x62, 0x62, 0x62), "Cinza Escuro"), ((0x69, 0x26, 0x0d), "Marrom Escuro"),
    ((0xff, 0x00, 0x60), "Rosa Escuro"), ((0xbf, 0x82, 0x00), "Marrom Claro"),
    ((0xf3, 0x91, 0x78), "Salmão"), ((0xff, 0x68, 0x05), "Vermelhão"),
    ((0xf0, 0xf0, 0xf0), "Branco"), ((0xc8, 0x32, 0xcd), "Violeta"),
    ((0xb0, 0xbf, 0x9b), "Verde Mar"), ((0x65, 0xbf, 0xeb), "Azul Céu"),
    ((0xff, 0xba, 0x04), "Abóbora"), ((0xff, 0xf0, 0x6c), "Amarelo Creme"),
    ((0xfe, 0xca, 0x15), "Cáqui"), ((0xf3, 0x81, 0x01), "Marrom Argila"),
    ((0x37, 0xa9, 0x23), "Verde Folha"), ((0x23, 0x46, 0x5f), "Azul Pavão"),
    ((0xa6, 0xa6, 0x95), "Cinza"), ((0xce, 0xbf, 0xa6), "Cinza Quente"),
    ((0x96, 0xaa, 0x02), "Oliva Escuro"), ((0xff, 0xe3, 0xc6), "Linho"),
    ((0xff, 0x99, 0xd7), "Rosa"), ((0x00, 0x70, 0x04), "Verde Escuro"),
    ((0xed, 0xcc, 0xfb), "Lavanda"), ((0xc0, 0x89, 0xd8), "Violeta Glicínia"),
    ((0xe7, 0xd9, 0xb4), "Bege"), ((0xe9, 0x0e, 0x86), "Carmim"),
    ((0xcf, 0x68, 0x29), "Vermelho Âmbar"), ((0x40, 0x86, 0x15), "Verde Oliva"),
    ((0xdb, 0x17, 0x97), "Fúcsia Escuro"), ((0xff, 0xa7, 0x04), "Tangerina"),
    ((0xb9, 0xff, 0xff), "Azul Claro"), ((0x22, 0x89, 0x27), "Verde Esmeralda"),
    ((0xb6, 0x12, 0xcd), "Púrpura"), ((0x00, 0xaa, 0x00), "Verde Musgo"),
    ((0xfe, 0xa9, 0xdc), "Rosa Pele"), ((0xfe, 0xd5, 0x10), "Ouro Colheita"),
    ((0x00, 0x97, 0xdf), "Azul Elétrico"), ((0xff, 0xff, 0x84), "Amarelo Limão"),
    ((0xcf, 0xe7, 0x74), "Verde Fresco"), ((0xff, 0xc8, 0x64), "Material Aplique"),
    ((0xff, 0xc8, 0xc8), "Posição Aplique"), ((0xff, 0xc8, 0xc8), "Aplique"),
]


def nearest_pec(rgb):
    """Índice PEC (1..61) da linha mais próxima, por distância perceptual simples."""
    r, g, b = rgb
    best, bi = 1e18, 1
    for i in range(1, 62):
        (R, G, B), _ = PEC_PALETTE[i]
        rm = (r + R) / 2
        d = (2 + rm / 256) * (r - R) ** 2 + 4 * (g - G) ** 2 + (2 + (255 - rm) / 256) * (b - B) ** 2
        if d < best:
            best, bi = d, i
    return bi


# ---------------------------------------------------------------------------
# Parâmetros padrão ("mesma base" do arquivo Cubra.pes: ~128 x 124 mm)
# ---------------------------------------------------------------------------
DEFAULTS = dict(
    largura_mm=128.0,      # largura máxima
    altura_mm=124.0,       # altura máxima
    n_cores=6,             # cores a separar (incluindo o fundo)
    ignorar_fundo=True,    # não bordar a cor de fundo
    espacamento_mm=0.4,    # distância entre linhas do preenchimento (densidade)
    ponto_mm=3.5,          # comprimento máximo do ponto
    area_min_pct=0.3,      # cores com menos que isso (% da imagem) são fundidas
    girar_90=False,        # gira o desenho 90° (como o Cubra.pes estava salvo)
    minhas_linhas=None,    # opcional: lista de índices PEC (linhas que você tem)
)


# ---------------------------------------------------------------------------
# 1) Preparar e separar cores
# ---------------------------------------------------------------------------
def carregar_imagem(caminho):
    im = Image.open(caminho)
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        fundo = Image.new("RGBA", im.size, (255, 255, 255, 255))
        fundo.alpha_composite(im)
        im = fundo
    return im.convert("RGB")


def recortar_conteudo(im, tol=40):
    """Corta as margens da cor de fundo para o desenho ocupar todo o tamanho escolhido."""
    a = np.asarray(im.convert("RGB"), dtype=np.int16)
    borda = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    ref = np.median(borda, axis=0)
    dif = np.abs(a - ref).sum(axis=2) > tol
    ys, xs = np.where(dif)
    if len(xs) == 0:
        return im
    m = 4
    x0, x1 = max(0, xs.min() - m), min(im.width, xs.max() + 1 + m)
    y0, y1 = max(0, ys.min() - m), min(im.height, ys.max() + 1 + m)
    return im.crop((int(x0), int(y0), int(x1), int(y1)))


def separar_cores(im, p):
    """Redimensiona para 1 px = 0,1 mm e reduz a n cores. Retorna (indices, paleta, id_fundo)."""
    if p["girar_90"]:
        im = im.rotate(90, expand=True)
    if p["ignorar_fundo"]:
        im = recortar_conteudo(im)
    w, h = im.size
    esc = min(p["largura_mm"] * 10 / w, p["altura_mm"] * 10 / h)
    nw, nh = max(1, int(round(w * esc))), max(1, int(round(h * esc)))
    im = im.resize((nw, nh), Image.LANCZOS).filter(ImageFilter.MedianFilter(5))

    fixas = p.get("minhas_linhas") or []
    if fixas:
        # usa somente as linhas escolhidas (+ a cor do fundo, para não confundir)
        a = np.asarray(im, dtype=np.int32)
        cores = [PEC_PALETTE[i][0] for i in fixas]
        if p["ignorar_fundo"]:
            borda = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
            cores = [tuple(int(v) for v in np.median(borda, axis=0))] + cores
        cand = np.array(cores, dtype=np.int32)
        rm = (a[:, :, None, 0] + cand[None, None, :, 0]) / 2
        dr = a[:, :, None, 0] - cand[None, None, :, 0]
        dg = a[:, :, None, 1] - cand[None, None, :, 1]
        db = a[:, :, None, 2] - cand[None, None, :, 2]
        dist = (2 + rm / 256) * dr * dr + 4 * dg * dg + (2 + (255 - rm) / 256) * db * db
        q = Image.fromarray(np.argmin(dist, axis=2).astype(np.uint8), "P")
        flat = [v for c in cores for v in c]
        q.putpalette(flat + [0] * (768 - len(flat)))
    else:
        n = int(p["n_cores"])
        q = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT, kmeans=3)
    q = q.filter(ImageFilter.ModeFilter(5))      # limpa pixels soltos/serrilhado
    idx = np.array(q, dtype=np.int16)
    pal = np.array(q.getpalette()[: 3 * 256], dtype=np.int32).reshape(-1, 3)

    # funde cores com área muito pequena na cor mais parecida
    total = idx.size
    while True:
        usados, cont = np.unique(idx, return_counts=True)
        peq = [(c, u) for u, c in zip(usados, cont) if c < total * p["area_min_pct"] / 100]
        if not peq or len(usados) <= 1:
            break
        c, u = min(peq)
        outros = [v for v in usados if v != u]
        alvo = min(outros, key=lambda v: int(((pal[v] - pal[u]) ** 2).sum()))
        idx[idx == u] = alvo

    # fundo = cor mais comum na borda
    borda = np.concatenate([idx[0], idx[-1], idx[:, 0], idx[:, -1]])
    vals, cnt = np.unique(borda, return_counts=True)
    fundo = int(vals[np.argmax(cnt)])
    return idx, pal, fundo


# ---------------------------------------------------------------------------
# 2) Preenchimento (tatami) por cor
# ---------------------------------------------------------------------------
def _segmentos_linha(linha):
    pad = np.concatenate(([0], linha.astype(np.int8), [0]))
    d = np.diff(pad)
    ini = np.where(d == 1)[0]
    fim = np.where(d == -1)[0] - 1
    return list(zip(ini.tolist(), fim.tolist()))


def _cadeias(mascara, passo):
    """Agrupa segmentos horizontais em 'colunas' contínuas de cima para baixo."""
    h = mascara.shape[0]
    linhas_y = list(range(passo // 2, h, passo))
    segs = []
    for y in linhas_y:
        segs.append([[a, b, False] for a, b in _segmentos_linha(mascara[y]) if b - a >= 2])
    cadeias = []
    for k in range(len(linhas_y)):
        for s in segs[k]:
            if s[2]:
                continue
            s[2] = True
            cad = [(linhas_y[k], s[0], s[1])]
            cur, kk = s, k
            while kk + 1 < len(linhas_y):
                prox = None
                for t in segs[kk + 1]:
                    if not t[2] and t[0] <= cur[1] and t[1] >= cur[0]:
                        prox = t
                        break
                if prox is None:
                    break
                prox[2] = True
                cad.append((linhas_y[kk + 1], prox[0], prox[1]))
                cur, kk = prox, kk + 1
            cadeias.append(cad)
    return cadeias


def _pontos_reta(x0, y0, x1, y1, L):
    d = math.hypot(x1 - x0, y1 - y0)
    n = max(1, int(math.ceil(d / L)))
    return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(1, n + 1)]


def _pontos_segmento(y, a, b, ida, L, comp=2):
    """Pontos ao longo de um segmento, com deslocamento em 'tijolo' entre linhas."""
    a, b = a - comp, b + comp
    off = ((y // 4) % 3) * L / 3.0
    meio = []
    m = math.ceil((a - off) / L)
    while True:
        x = off + m * L
        if x >= b:
            break
        if x - a >= 6 and b - x >= 6:
            meio.append(x)
        m += 1
    xs = [a] + meio + [b]
    if not ida:
        xs = xs[::-1]
    return [(x, y) for x in xs]


def cores_detectadas(idx, pal, fundo):
    """Lista das cores encontradas: [{id, rgb, pct, fundo}], da maior área para a menor."""
    usados, cont = np.unique(idx, return_counts=True)
    tot = float(idx.size)
    res = [dict(id=int(u), rgb=tuple(int(v) for v in pal[u]), pct=100.0 * c / tot, fundo=(int(u) == fundo))
           for u, c in zip(usados.tolist(), cont.tolist())]
    res.sort(key=lambda r: -r["pct"])
    return res


def selecao_padrao(cores, p):
    """Seleção inicial: cada cor vira uma linha Brother (a mais próxima); o fundo não é bordado."""
    sel = []
    for c in cores:
        pec = nearest_pec(c["rgb"])
        sel.append(dict(ids=[c["id"]], rgb_img=c["rgb"], pct=c["pct"], fundo=c["fundo"],
                        pec=pec, rgb=PEC_PALETTE[pec][0], nome=PEC_PALETTE[pec][1],
                        bordar=not (c["fundo"] and p["ignorar_fundo"])))
    return sel


def _agrupar_selecao(selecao):
    """Cores que receberam a mesma linha são bordadas juntas (menos trocas de linha)."""
    grupos = []
    for s in selecao:
        if not s.get("bordar", True):
            continue
        chave = (s.get("pec"), tuple(s["rgb"]))
        for g in grupos:
            if g["chave"] == chave:
                g["ids"] += list(s["ids"])
                break
        else:
            grupos.append(dict(chave=chave, ids=list(s["ids"]), rgb=tuple(s["rgb"]),
                               pec=s.get("pec"), nome=s.get("nome", "")))
    return grupos


def gerar_pontos(idx, pal, fundo, p, selecao=None):
    """Retorna (comandos, cores). Comandos: ('S',x,y) ponto, ('J',x,y) salto com corte, ('C',) troca de cor."""
    passo = max(2, int(round(p["espacamento_mm"] * 10)))
    L = p["ponto_mm"] * 10
    if selecao is None:
        selecao = selecao_padrao(cores_detectadas(idx, pal, fundo), p)
    grupos = _agrupar_selecao(selecao)

    cmds, cores = [], []
    pos = (idx.shape[1] / 2, idx.shape[0] / 2)
    for gi, g in enumerate(grupos):
        cadeias = _cadeias(np.isin(idx, g["ids"]), passo)
        # o deslocamento pode passar por baixo desta cor ou de cores que ainda serão bordadas
        futuros = [i for gg in grupos[gi:] for i in gg["ids"]]
        if not cadeias:
            continue
        if cores:
            cmds.append(("C",))
        cores.append(dict(rgb=g["rgb"], pec=g["pec"] or nearest_pec(g["rgb"]), nome=g["nome"]))
        pend = cadeias
        primeiro = True
        mask = np.isin(idx, futuros)
        hh, ww = mask.shape

        def por_dentro(p0, p1):
            """True se a reta entre p0 e p1 fica dentro da área desta cor (o ponto fica escondido)."""
            n = int(max(abs(p1[0] - p0[0]), abs(p1[1] - p0[1]))) + 1
            for t in np.linspace(0, 1, n):
                x = int(round(p0[0] + (p1[0] - p0[0]) * t))
                y = int(round(p0[1] + (p1[1] - p0[1]) * t))
                if not (0 <= x < ww and 0 <= y < hh):
                    return False
                if not mask[max(0, y - 1):y + 2, max(0, x - 1):x + 2].any():
                    return False
            return True

        while pend:
            # entrada mais próxima: qualquer ponta da 1ª ou da última linha de cada cadeia
            melhor = None
            for ci_, cad in enumerate(pend):
                for inv in (False, True):
                    yy, aa, bb = cad[-1] if inv else cad[0]
                    for xx in (aa, bb):
                        dd = (xx - pos[0]) ** 2 + (yy - pos[1]) ** 2
                        if melhor is None or dd < melhor[0]:
                            melhor = (dd, ci_, inv, xx == aa)
            _, j, inv, pela_esq = melhor
            cad = pend.pop(j)
            if inv:
                cad = cad[::-1]
            y0, a0, b0 = cad[0]
            ida = pela_esq
            inicio = (a0 - 2 if ida else b0 + 2, y0)
            dist = math.hypot(inicio[0] - pos[0], inicio[1] - pos[1])
            pula = primeiro or (dist > 20 and not (dist <= 100 and por_dentro(pos, inicio)))
            if pula:
                if not primeiro:
                    # arremate antes do corte
                    cmds += [("S", pos[0] + 2, pos[1]), ("S", pos[0], pos[1])]
                cmds.append(("J", inicio[0], inicio[1]))
                # arremate de entrada
                cmds += [("S", inicio[0], inicio[1]), ("S", inicio[0] + (2 if ida else -2), inicio[1]),
                         ("S", inicio[0], inicio[1])]
                pos = inicio
                primeiro = False
            for y, a, b in cad:
                pts = _pontos_segmento(y, a, b, ida, L)
                for q in _pontos_reta(pos[0], pos[1], pts[0][0], pts[0][1], L):
                    cmds.append(("S",) + q)
                for q in pts[1:]:
                    cmds.append(("S",) + q)
                pos = pts[-1]
                ida = not ida
        cmds += [("S", pos[0] - 2, pos[1]), ("S", pos[0], pos[1])]
    return cmds, cores


# ---------------------------------------------------------------------------
# 3) Gravação PES (cabeçalho v1) + PEC
# ---------------------------------------------------------------------------
def _long(v, flag=0):
    return (0x8000 | (flag << 8) | (v & 0x0FFF)).to_bytes(2, "big")


def _icone(cmds_abs, ext):
    """Ícone 48x38 monocromático usado no visor da máquina."""
    im = Image.new("1", (48, 38), 0)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, 47, 37], outline=1)
    minx, miny, maxx, maxy = ext
    s = min(40 / max(1, maxx - minx), 30 / max(1, maxy - miny))
    ox = 24 - (minx + maxx) / 2 * s
    oy = 19 - (miny + maxy) / 2 * s
    ant = None
    for c in cmds_abs:
        if c[0] == "S":
            P = (c[1] * s + ox, c[2] * s + oy)
            if ant:
                dr.line([ant, P], fill=1)
            ant = P
        elif c[0] == "J":
            ant = None
    px = im.load()
    out = bytearray(228)
    for y in range(38):
        for x in range(48):
            if px[x, y]:
                out[y * 6 + x // 8] |= 1 << (x % 8)
    return bytes(out)


def gravar_pes(caminho, cmds, cores, nome="Bordado"):
    # coordenadas inteiras centradas em (0,0)
    xs = [c[1] for c in cmds if c[0] != "C"]
    ys = [c[2] for c in cmds if c[0] != "C"]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    absl = []
    for c in cmds:
        absl.append(c if c[0] == "C" else (c[0], int(round(c[1] - cx)), int(round(c[2] - cy))))
    xs = [c[1] for c in absl if c[0] != "C"]
    ys = [c[2] for c in absl if c[0] != "C"]
    ext = (min(xs), min(ys), max(xs), max(ys))

    # --- codificação dos pontos ---
    st = bytearray()
    xx = yy = 0
    troca2 = True
    inicio = True
    for c in absl:
        if c[0] == "C":
            st += b"\xfe\xb0" + (b"\x02" if troca2 else b"\x01")
            troca2 = not troca2
            continue
        dx, dy = c[1] - xx, c[2] - yy
        if c[0] == "J":
            flag = 0x10 if inicio else 0x20
            # saltos maiores que 204 mm são divididos
            n = max(1, int(math.ceil(max(abs(dx), abs(dy)) / 2000)))
            for i in range(n):
                ddx = int(round(dx * (i + 1) / n)) - int(round(dx * i / n))
                ddy = int(round(dy * (i + 1) / n)) - int(round(dy * i / n))
                st += _long(ddx, flag) + _long(ddy, flag)
        else:
            if dx == 0 and dy == 0:
                continue
            n = max(1, int(math.ceil(max(abs(dx), abs(dy)) / 120)))  # segurança
            for i in range(n):
                ddx = int(round(dx * (i + 1) / n)) - int(round(dx * i / n))
                ddy = int(round(dy * (i + 1) / n)) - int(round(dy * i / n))
                if -63 <= ddx <= 63 and -63 <= ddy <= 63:
                    st += bytes([ddx & 0x7F, ddy & 0x7F])
                else:
                    st += _long(ddx) + _long(ddy)
        xx, yy = c[1], c[2]
        inicio = False
    st += b"\xff"

    # --- cabeçalho PEC (512 bytes) ---
    idx_pec = [c["pec"] if isinstance(c, dict) else nearest_pec(c) for c in cores]
    pec = bytearray()
    pec += ("LA:%-16s\r" % nome[:16]).encode("latin1", "replace")
    pec += b"\x20" * 12 + b"\xff\x00" + bytes([6, 38])
    pec += b"\x20\x20\x20\x20\x64\x20\x00\x20\x00\x20\x20\x20"
    pec += bytes([len(idx_pec) - 1] + idx_pec)
    pec += b"\x20" * (512 - len(pec))

    # --- bloco de pontos (cabeçalho de 20 bytes) ---
    w, h = ext[2] - ext[0], ext[3] - ext[1]
    bloco = bytearray(b"\x00\x00") + b"\x00\x00\x00" + b"\x31\xff\xf0"
    bloco += w.to_bytes(2, "little") + h.to_bytes(2, "little")
    bloco += (0x1E0).to_bytes(2, "little") + (0x1B0).to_bytes(2, "little")
    bloco += (0x9000 | (-ext[0] & 0x0FFF)).to_bytes(2, "big")
    bloco += (0x9000 | (-ext[1] & 0x0FFF)).to_bytes(2, "big")
    bloco += st
    bloco[2:5] = len(bloco).to_bytes(3, "little")

    # --- ícones: desenho completo + um por cor ---
    graf = _icone(absl, ext)
    partes, atual = [], []
    for c in absl:
        if c[0] == "C":
            partes.append(atual)
            atual = []
        else:
            atual.append(c)
    partes.append(atual)
    for parte in partes:
        graf += _icone(parte, ext)

    cab = b"#PES0001" + (22).to_bytes(4, "little") + b"\x00" * 10
    with open(caminho, "wb") as f:
        f.write(cab + pec + bloco + graf)
    return idx_pec


# ---------------------------------------------------------------------------
# 4) Leitura / análise de .pes
# ---------------------------------------------------------------------------
def ler_pes(caminho):
    d = open(caminho, "rb").read()
    if not d.startswith(b"#PES"):
        raise ValueError("Não é um arquivo PES.")
    versao = d[4:8].decode("latin1")
    p = int.from_bytes(d[8:12], "little")
    nome = d[p + 3:p + 19].decode("latin1", "replace").strip()
    nc = d[p + 48] + 1
    idx_pec = list(d[p + 49:p + 49 + nc])

    # cores RGB gravadas na parte PES (versões novas), se existirem
    linhas = []
    if versao >= "0050":
        try:
            linhas = _linhas_pes(d[:p])
        except Exception:
            linhas = []
    unicos = []
    for v in idx_pec:
        if v not in unicos:
            unicos.append(v)

    def cor_bloco(k):
        v = idx_pec[k] if k < len(idx_pec) else 20
        if linhas and len(linhas) == len(unicos):
            return linhas[unicos.index(v)]
        rgb, nm = PEC_PALETTE[v] if 0 < v < len(PEC_PALETTE) else ((0, 0, 0), "?")
        return ("PEC %d" % v, rgb, nm)

    f = p + 512 + 20
    x = y = 0
    blocos = [[]]
    saltos = cortes = pontos = 0
    while f + 1 < len(d):
        v1, v2 = d[f], d[f + 1]
        f += 2
        if v1 == 0xFF:
            break
        if v1 == 0xFE and v2 == 0xB0:
            f += 1
            blocos.append([])
            continue
        salto = corte = False
        if v1 & 0x80:
            salto |= bool(v1 & 0x30); corte |= bool(v1 & 0x20)
            dx = ((v1 << 8) | v2) & 0xFFF
            dx -= 0x1000 if dx > 0x7FF else 0
            v2 = d[f]; f += 1
        else:
            dx = v1 - 0x80 if v1 > 0x3F else v1
        if v2 & 0x80:
            salto |= bool(v2 & 0x30); corte |= bool(v2 & 0x20)
            dy = ((v2 << 8) | d[f]) & 0xFFF; f += 1
            dy -= 0x1000 if dy > 0x7FF else 0
        else:
            dy = v2 - 0x80 if v2 > 0x3F else v2
        x += dx; y += dy
        if salto:
            saltos += 1
            cortes += corte
            blocos[-1].append(None)
        else:
            pontos += 1
        blocos[-1].append((x, y))
    pts = [q for b in blocos for q in b if q]
    ext = (min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts))
    info = dict(
        versao=versao, nome=nome, pontos=pontos, saltos=saltos, cortes=cortes,
        largura_mm=(ext[2] - ext[0]) / 10, altura_mm=(ext[3] - ext[1]) / 10,
        blocos=[(cor_bloco(k), sum(1 for q in b if q)) for k, b in enumerate(blocos)],
    )
    return info, blocos, ext


def _linhas_pes(d):
    """Extrai (código, RGB, marca) da lista de linhas das versões PES 5+ (heurística)."""
    i = d.find(b"\x0a\x00\x00\x00")
    if i < 0:
        return []
    # a 1ª entrada começa com [tamanho][código numérico][R G B 00][0A 00 00 00]
    start = None
    for s in range(max(2, i - 20), i):
        L = d[s]
        if 1 <= L <= 12 and s + 1 + L + 4 == i and d[s + 1:s + 1 + L].isalnum():
            start = s
            break
    if start is None:
        return []
    n = int.from_bytes(d[start - 2:start], "little")
    k = start
    res = []
    for _ in range(n):
        L = d[k]; cod = d[k + 1:k + 1 + L].decode("latin1"); k += 1 + L
        rgb = tuple(d[k:k + 3]); k += 4 + 4
        L = d[k]; desc = d[k + 1:k + 1 + L].decode("latin1"); k += 1 + L
        L = d[k]; marca = d[k + 1:k + 1 + L].decode("latin1"); k += 1 + L
        L = d[k]; k += 1 + L
        res.append((cod, rgb, marca))
    return res


# ---------------------------------------------------------------------------
# 5) Prévia
# ---------------------------------------------------------------------------
def renderizar(blocos, cores_rgb, ext, escala=0.6, fundo=(236, 236, 232), margem=30):
    minx, miny, maxx, maxy = ext
    W = int((maxx - minx) * escala) + 2 * margem
    H = int((maxy - miny) * escala) + 2 * margem
    im = Image.new("RGB", (max(W, 10), max(H, 10)), fundo)
    dr = ImageDraw.Draw(im)
    lw = max(1, int(round(escala * 4.5)))
    for k, b in enumerate(blocos):
        cor = cores_rgb[k] if k < len(cores_rgb) else (0, 0, 0)
        if sum(cor) > 690 and sum(fundo) > 690:
            cor = (225, 225, 225)
        ant = None
        for q in b:
            if q is None:
                ant = None
                continue
            P = ((q[0] - minx) * escala + margem, (q[1] - miny) * escala + margem)
            if ant:
                dr.line([ant, P], fill=cor, width=lw)
            ant = P
    return im


def preparar(caminho_img, params=None):
    """Etapa 1: carrega a imagem e separa as cores (pode ser reaproveitada)."""
    p = dict(DEFAULTS)
    if params:
        p.update(params)
    idx, pal, fundo = separar_cores(carregar_imagem(caminho_img), p)
    return dict(idx=idx, pal=pal, fundo=fundo, cores=cores_detectadas(idx, pal, fundo), p=p)


def previa_cores(prep, selecao, fundo_rgb=(236, 236, 232)):
    """Imagem do desenho já com as linhas escolhidas (cores não bordadas ficam com a cor do tecido)."""
    idx = prep["idx"]
    lut = np.zeros((int(idx.max()) + 1, 3), dtype=np.uint8)
    lut[:] = fundo_rgb
    for s in selecao:
        if s.get("bordar", True):
            for i in s["ids"]:
                lut[i] = s["rgb"]
    return Image.fromarray(lut[idx], "RGB")


def gerar(prep, selecao, caminho_pes, params=None, nome="Bordado"):
    """Etapa 2: gera os pontos com as cores escolhidas e grava o .pes."""
    p = dict(prep["p"])
    if params:
        p.update(params)
    cmds, cores = gerar_pontos(prep["idx"], prep["pal"], prep["fundo"], p, selecao)
    if not cmds:
        raise ValueError("Nenhuma cor marcada para bordar.")
    gravar_pes(caminho_pes, cmds, cores, nome or "Bordado")
    info, blocos, ext = ler_pes(caminho_pes)
    # mostra as cores escolhidas (inclusive personalizadas) em vez da paleta PEC
    info["blocos"] = [(("PEC %d" % c["pec"], tuple(c["rgb"]), c["nome"] or PEC_PALETTE[c["pec"]][1]), n)
                      for c, (_, n) in zip(cores, info["blocos"])]
    return info, blocos, ext


def converter(caminho_img, caminho_pes, params=None, nome=None):
    prep = preparar(caminho_img, params)
    return gerar(prep, selecao_padrao(prep["cores"], prep["p"]), caminho_pes, None, nome)


if __name__ == "__main__":
    # Uso em linha de comando: python bordado_core.py imagem.png saida.pes [n_cores]
    import sys
    if len(sys.argv) < 3:
        print("Uso: python bordado_core.py imagem.png saida.pes [n_cores]")
        sys.exit(1)
    prm = {"n_cores": int(sys.argv[3])} if len(sys.argv) > 3 else {}
    info, _, _ = converter(sys.argv[1], sys.argv[2], prm)
    print("%.1f x %.1f mm, %d pontos, %d cores" % (info["largura_mm"], info["altura_mm"], info["pontos"], len(info["blocos"])))
