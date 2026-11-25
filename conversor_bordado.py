# -*- coding: utf-8 -*-
"""Conversor de Bordado - interface gráfica (Tkinter)."""
import os
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from PIL import Image, ImageDraw, ImageTk

import bordado_core as core

PREVIA_MAX = 520
CHAVES_SEPARACAO = ("largura_mm", "altura_mm", "n_cores", "area_min_pct", "ignorar_fundo", "girar_90")


def hexrgb(rgb):
    return "#%02X%02X%02X" % tuple(rgb)


def texto_contraste(rgb):
    return "#000000" if (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) > 140 else "#FFFFFF"


# ---------------------------------------------------------------------------
# Janela: grade com as linhas Brother (escolha única ou múltipla)
# ---------------------------------------------------------------------------
class GradeLinhas(tk.Toplevel):
    def __init__(self, pai, titulo, multipla=False, marcadas=None, atual=None, rgb_origem=None):
        super().__init__(pai)
        self.title(titulo)
        self.transient(pai)
        self.resizable(False, False)
        self.resultado = None
        self.multipla = multipla
        self.marcadas = set(marcadas or [])
        self.celulas = {}

        if rgb_origem is not None:
            topo = ttk.Frame(self, padding=(10, 8, 10, 0))
            topo.pack(fill="x")
            ttk.Label(topo, text="Cor na imagem:").pack(side="left")
            tk.Label(topo, bg=hexrgb(rgb_origem), width=6, relief="solid", bd=1).pack(side="left", padx=6)
            sug = core.nearest_pec(rgb_origem)
            ttk.Label(topo, text="Linha mais próxima: %d - %s" % (sug, core.PEC_PALETTE[sug][1])).pack(side="left", padx=8)
        elif multipla:
            ttk.Label(self, padding=(10, 8, 10, 0), wraplength=640,
                      text="Marque as linhas que você tem. O desenho será convertido usando somente "
                           "essas cores (cada parte da imagem vai para a linha mais parecida).").pack(anchor="w")

        grade = ttk.Frame(self, padding=10)
        grade.pack()
        for i in range(1, 62):
            rgb, nome = core.PEC_PALETTE[i]
            cel = tk.Label(grade, text="%d\n%s" % (i, nome), bg=hexrgb(rgb), fg=texto_contraste(rgb),
                           width=13, height=3, font=("Segoe UI", 8), relief="flat", bd=3, cursor="hand2")
            cel.grid(row=(i - 1) // 8, column=(i - 1) % 8, padx=2, pady=2)
            cel.bind("<Button-1>", lambda e, k=i: self._clique(k))
            self.celulas[i] = cel
            if (multipla and i in self.marcadas) or (not multipla and i == atual):
                self._marcar(i, True)

        rod = ttk.Frame(self, padding=(10, 0, 10, 10))
        rod.pack(fill="x")
        if multipla:
            self.lb_qtd = ttk.Label(rod, text="")
            self.lb_qtd.pack(side="left")
            self._atualiza_qtd()
            ttk.Button(rod, text="OK", command=self._ok).pack(side="right")
            ttk.Button(rod, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
            ttk.Button(rod, text="Desmarcar todas", command=self._limpar).pack(side="right", padx=4)
        else:
            ttk.Button(rod, text="Cor personalizada...", command=self._personalizada).pack(side="left")
            ttk.Button(rod, text="Cancelar", command=self.destroy).pack(side="right")

        self.grab_set()
        self.focus_set()

    def _marcar(self, i, sim):
        self.celulas[i].configure(relief="sunken" if sim else "flat", bd=5 if sim else 3,
                                  highlightthickness=0)
        rgb, nome = core.PEC_PALETTE[i]
        self.celulas[i].configure(text=("✔ %d\n%s" if sim else "%d\n%s") % (i, nome))

    def _clique(self, i):
        if self.multipla:
            if i in self.marcadas:
                self.marcadas.discard(i)
                self._marcar(i, False)
            else:
                self.marcadas.add(i)
                self._marcar(i, True)
            self._atualiza_qtd()
        else:
            rgb, nome = core.PEC_PALETTE[i]
            self.resultado = dict(pec=i, rgb=rgb, nome=nome)
            self.destroy()

    def _atualiza_qtd(self):
        self.lb_qtd.configure(text="%d linha(s) marcada(s)" % len(self.marcadas))

    def _limpar(self):
        for i in list(self.marcadas):
            self._marcar(i, False)
        self.marcadas.clear()
        self._atualiza_qtd()

    def _ok(self):
        self.resultado = sorted(self.marcadas)
        self.destroy()

    def _personalizada(self):
        c = colorchooser.askcolor(parent=self, title="Escolha a cor da linha")
        if c and c[0]:
            rgb = tuple(int(v) for v in c[0])
            pec = core.nearest_pec(rgb)
            self.resultado = dict(pec=pec, rgb=rgb, nome="Personalizada %s (máquina: %s)" % (hexrgb(rgb), core.PEC_PALETTE[pec][1]))
            self.destroy()


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Conversor de Bordado - Imagem para .PES")
        self.geometry("1240x820")
        self.minsize(1040, 700)
        self.caminho_img = None
        self.pes_tmp = os.path.join(tempfile.gettempdir(), "conversor_bordado_tmp.pes")
        self.pes_pronto = False
        self.prep = None
        self.prep_chave = None
        self.selecao = []
        self.minhas_linhas = []
        self.prev_img = None
        self._fotos = {}
        self._swatches = []
        self._montar()

    # ------------------------------------------------------------------ UI
    def _montar(self):
        lado = ttk.Frame(self, padding=10)
        lado.pack(side="left", fill="y")

        ttk.Button(lado, text="Abrir imagem...", command=self.abrir_imagem).pack(fill="x")
        ttk.Button(lado, text="Analisar arquivo .pes...", command=self.abrir_pes).pack(fill="x", pady=(6, 12))

        ttk.Label(lado, text="Parâmetros", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.v = {
            "nome": tk.StringVar(value="Bordado"),
            "largura_mm": tk.DoubleVar(value=core.DEFAULTS["largura_mm"]),
            "altura_mm": tk.DoubleVar(value=core.DEFAULTS["altura_mm"]),
            "n_cores": tk.IntVar(value=core.DEFAULTS["n_cores"]),
            "espacamento_mm": tk.DoubleVar(value=core.DEFAULTS["espacamento_mm"]),
            "ponto_mm": tk.DoubleVar(value=core.DEFAULTS["ponto_mm"]),
            "area_min_pct": tk.DoubleVar(value=core.DEFAULTS["area_min_pct"]),
            "ignorar_fundo": tk.BooleanVar(value=True),
            "girar_90": tk.BooleanVar(value=False),
        }
        campos = [
            ("Nome do desenho", "nome", None),
            ("Largura máx. (mm)", "largura_mm", (20, 400, 1)),
            ("Altura máx. (mm)", "altura_mm", (20, 400, 1)),
            ("Nº de cores (com fundo)", "n_cores", (2, 16, 1)),
            ("Espaçamento das linhas (mm)", "espacamento_mm", (0.2, 1.0, 0.05)),
            ("Comprimento do ponto (mm)", "ponto_mm", (1.5, 7.0, 0.5)),
            ("Juntar cores menores que (%)", "area_min_pct", (0.0, 5.0, 0.1)),
        ]
        for rot, chave, faixa in campos:
            ttk.Label(lado, text=rot).pack(anchor="w", pady=(5, 0))
            if faixa is None:
                ttk.Entry(lado, textvariable=self.v[chave]).pack(fill="x")
            else:
                ttk.Spinbox(lado, from_=faixa[0], to=faixa[1], increment=faixa[2],
                            textvariable=self.v[chave], width=10).pack(fill="x")
        ttk.Checkbutton(lado, text="Não bordar a cor de fundo", variable=self.v["ignorar_fundo"]).pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(lado, text="Girar 90° (bastidor)", variable=self.v["girar_90"]).pack(anchor="w")
        ttk.Button(lado, text="Padrão Cubra (128 × 124 mm)", command=self.padrao).pack(fill="x", pady=(8, 0))

        ttk.Label(lado, text="Linhas disponíveis", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 0))
        ttk.Button(lado, text="Usar só as minhas linhas...", command=self.escolher_minhas_linhas).pack(fill="x", pady=(2, 0))
        self.lb_minhas = ttk.Label(lado, text="Automático (cores da imagem)", foreground="#555")
        self.lb_minhas.pack(anchor="w")

        self.bt_separar = ttk.Button(lado, text="1. Separar cores", command=self.separar)
        self.bt_separar.pack(fill="x", pady=(14, 4))
        self.bt_gerar = ttk.Button(lado, text="2. Gerar bordado", command=self.gerar)
        self.bt_gerar.pack(fill="x")
        self.bt_salvar = ttk.Button(lado, text="3. Salvar .pes...", command=self.salvar, state="disabled")
        self.bt_salvar.pack(fill="x", pady=(4, 0))
        self.bt_png = ttk.Button(lado, text="Salvar prévia .png...", command=self.salvar_png, state="disabled")
        self.bt_png.pack(fill="x", pady=(4, 0))

        self.status = tk.StringVar(value="Abra uma imagem (PNG/JPG) ou um arquivo .pes.")
        ttk.Label(lado, textvariable=self.status, wraplength=230, foreground="#555").pack(anchor="w", pady=(10, 0))

        # área central: original | prévia
        centro = ttk.Frame(self, padding=(0, 10, 10, 10))
        centro.pack(side="left", fill="both", expand=True)
        topo = ttk.Frame(centro)
        topo.pack(fill="both", expand=True)
        self.lb_orig = self._painel(topo, "Imagem original")
        self.lb_prev = self._painel(topo, "Prévia")

        self.abas = ttk.Notebook(centro)
        self.abas.pack(fill="x", pady=(8, 0))
        self._aba_cores()
        self._aba_analise()

    def _aba_cores(self):
        f = ttk.Frame(self.abas, padding=6)
        self.abas.add(f, text="Cores do bordado")
        ttk.Label(f, foreground="#555",
                  text="Duplo clique troca a linha. Cores com a mesma linha são bordadas juntas. "
                       "A ordem da lista é a ordem de bordado.").pack(anchor="w")
        corpo = ttk.Frame(f)
        corpo.pack(fill="x", pady=(4, 0))
        cols = ("bordar", "area", "linha")
        st = ttk.Style(self)
        st.configure("Cores.Treeview", rowheight=24)
        self.tv_cores = ttk.Treeview(corpo, columns=cols, show="tree headings", height=7, style="Cores.Treeview",
                                     selectmode="extended")
        self.tv_cores.heading("#0", text="Imagem → Linha")
        self.tv_cores.column("#0", width=110, anchor="w")
        for c, t, w in zip(cols, ("Bordar", "Área", "Linha escolhida"), (70, 70, 360)):
            self.tv_cores.heading(c, text=t)
            self.tv_cores.column(c, width=w, anchor="w")
        self.tv_cores.pack(side="left", fill="x", expand=True)
        self.tv_cores.bind("<Double-1>", lambda e: self.trocar_linha())
        self.tv_cores.bind("<space>", lambda e: self.alternar_bordar())

        bts = ttk.Frame(corpo, padding=(8, 0, 0, 0))
        bts.pack(side="left", fill="y")
        for txt, cmd in (("Trocar linha...", self.trocar_linha),
                         ("Bordar / Não bordar", self.alternar_bordar),
                         ("Mesma linha da 1ª selecionada", self.igualar_linhas),
                         ("▲ Subir", lambda: self.mover(-1)),
                         ("▼ Descer", lambda: self.mover(1)),
                         ("Restaurar cores", self.restaurar)):
            ttk.Button(bts, text=txt, command=cmd).pack(fill="x", pady=2)

    def _aba_analise(self):
        f = ttk.Frame(self.abas, padding=6)
        self.abas.add(f, text="Análise do arquivo")
        self.resumo = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.resumo, wraplength=900).pack(anchor="w")
        cols = ("n", "cor", "linha", "pontos")
        self.tab = ttk.Treeview(f, columns=cols, show="headings", height=7)
        for c, t, w in zip(cols, ("#", "Cor (RGB)", "Linha / código", "Pontos"), (40, 110, 380, 90)):
            self.tab.heading(c, text=t)
            self.tab.column(c, width=w, anchor="w")
        self.tab.pack(fill="x", pady=(4, 0))

    def _painel(self, pai, titulo):
        f = ttk.LabelFrame(pai, text=titulo, padding=4)
        f.pack(side="left", fill="both", expand=True, padx=4)
        lb = tk.Label(f, bg="#ececea")
        lb.pack(fill="both", expand=True)
        return lb

    def _mostrar(self, lb, im, chave):
        im = im.copy()
        im.thumbnail((PREVIA_MAX, PREVIA_MAX - 120))
        foto = ImageTk.PhotoImage(im)
        self._fotos[chave] = foto
        lb.configure(image=foto)

    def padrao(self):
        self.v["largura_mm"].set(128.0)
        self.v["altura_mm"].set(124.0)
        self.v["espacamento_mm"].set(0.4)
        self.v["ponto_mm"].set(3.5)

    # ---------------------------------------------------------- parâmetros
    def _params(self):
        p = {k: var.get() for k, var in self.v.items() if k != "nome"}
        p["minhas_linhas"] = list(self.minhas_linhas)
        return p

    def _chave(self, p):
        return (self.caminho_img,) + tuple(p[k] for k in CHAVES_SEPARACAO) + (tuple(p["minhas_linhas"]),)

    def escolher_minhas_linhas(self):
        dlg = GradeLinhas(self, "Minhas linhas", multipla=True, marcadas=self.minhas_linhas)
        self.wait_window(dlg)
        if dlg.resultado is None:
            return
        self.minhas_linhas = dlg.resultado
        if self.minhas_linhas:
            nomes = ", ".join(core.PEC_PALETTE[i][1] for i in self.minhas_linhas[:4])
            mais = "..." if len(self.minhas_linhas) > 4 else ""
            self.lb_minhas.configure(text="%d linhas: %s%s" % (len(self.minhas_linhas), nomes, mais))
        else:
            self.lb_minhas.configure(text="Automático (cores da imagem)")
        if self.caminho_img:
            self.separar()

    # ------------------------------------------------------------ cores
    def _swatch(self, s):
        im = Image.new("RGB", (64, 18), (236, 236, 232))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, 27, 17], fill=tuple(s["rgb_img"]), outline=(120, 120, 120))
        dr.polygon([(30, 5), (36, 9), (30, 13)], fill=(80, 80, 80))
        if s["bordar"]:
            dr.rectangle([40, 0, 63, 17], fill=tuple(s["rgb"]), outline=(120, 120, 120))
        else:
            dr.rectangle([40, 0, 63, 17], outline=(150, 150, 150))
            dr.line([40, 0, 63, 17], fill=(200, 60, 60), width=2)
        return ImageTk.PhotoImage(im)

    def _preencher_cores(self, manter=None):
        self.tv_cores.delete(*self.tv_cores.get_children())
        self._swatches = []
        for i, s in enumerate(self.selecao):
            foto = self._swatch(s)
            self._swatches.append(foto)
            linha = "%d - %s" % (s["pec"], s["nome"]) if s["bordar"] else "(não bordar)"
            if s.get("fundo"):
                linha += "   [fundo]"
            self.tv_cores.insert("", "end", iid=str(i), image=foto,
                                 values=("Sim" if s["bordar"] else "Não", "%.1f %%" % s["pct"], linha))
        if manter:
            sel = [str(i) for i in manter if 0 <= i < len(self.selecao)]
            if sel:
                self.tv_cores.selection_set(sel)
                self.tv_cores.see(sel[0])
        self._atualizar_previa_cores()

    def _atualizar_previa_cores(self):
        if self.prep:
            self._mostrar(self.lb_prev, core.previa_cores(self.prep, self.selecao), "prev")
            self.pes_pronto = False
            self.bt_salvar.configure(state="disabled")

    def _selecionados(self):
        return sorted(int(i) for i in self.tv_cores.selection())

    def trocar_linha(self):
        sel = self._selecionados()
        if not sel:
            messagebox.showinfo("Cores", "Selecione uma cor na lista.")
            return
        s0 = self.selecao[sel[0]]
        dlg = GradeLinhas(self, "Escolher linha", atual=s0["pec"], rgb_origem=s0["rgb_img"])
        self.wait_window(dlg)
        if dlg.resultado:
            for i in sel:
                self.selecao[i].update(dlg.resultado)
                self.selecao[i]["bordar"] = True
            self._preencher_cores(sel)

    def alternar_bordar(self):
        sel = self._selecionados()
        if not sel:
            return
        novo = not self.selecao[sel[0]]["bordar"]
        for i in sel:
            self.selecao[i]["bordar"] = novo
        self._preencher_cores(sel)

    def igualar_linhas(self):
        sel = self._selecionados()
        if len(sel) < 2:
            messagebox.showinfo("Cores", "Selecione duas ou mais cores (Ctrl+clique). "
                                         "Todas receberão a linha da primeira e serão bordadas juntas.")
            return
        s0 = self.selecao[sel[0]]
        for i in sel[1:]:
            self.selecao[i].update(pec=s0["pec"], rgb=s0["rgb"], nome=s0["nome"], bordar=True)
        self._preencher_cores(sel)

    def mover(self, d):
        sel = self._selecionados()
        if len(sel) != 1:
            return
        i, j = sel[0], sel[0] + d
        if 0 <= j < len(self.selecao):
            self.selecao[i], self.selecao[j] = self.selecao[j], self.selecao[i]
            self._preencher_cores([j])

    def restaurar(self):
        if self.prep:
            self.selecao = core.selecao_padrao(self.prep["cores"], self.prep["p"])
            self._preencher_cores()

    # ------------------------------------------------------------ ações
    def abrir_imagem(self):
        c = filedialog.askopenfilename(title="Escolha a imagem",
                                       filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("Todos", "*.*")])
        if not c:
            return
        self.caminho_img = c
        self.prep = None
        self.v["nome"].set(os.path.splitext(os.path.basename(c))[0][:16])
        self._mostrar(self.lb_orig, core.carregar_imagem(c), "orig")
        self.separar()

    def _rodar(self, trabalho, ao_terminar, msg):
        for b in (self.bt_separar, self.bt_gerar):
            b.configure(state="disabled")
        self.status.set(msg)

        def tarefa():
            try:
                r = trabalho()
                self.after(0, lambda: ao_terminar(r))
            except Exception as e:
                m = str(e)
                self.after(0, lambda: (messagebox.showerror("Erro", m), self.status.set("Erro.")))
            finally:
                self.after(0, lambda: [b.configure(state="normal") for b in (self.bt_separar, self.bt_gerar)])

        threading.Thread(target=tarefa, daemon=True).start()

    def separar(self, depois=None):
        if not self.caminho_img:
            messagebox.showinfo("Conversor", "Abra uma imagem primeiro.")
            return
        try:
            p = self._params()
        except tk.TclError:
            messagebox.showerror("Conversor", "Verifique os valores numéricos.")
            return
        chave = self._chave(p)

        def fim(prep):
            self.prep, self.prep_chave = prep, chave
            self.selecao = core.selecao_padrao(prep["cores"], prep["p"])
            self._preencher_cores()
            self.abas.select(0)
            self.status.set("%d cores encontradas. Ajuste as linhas na aba 'Cores do bordado' e clique em "
                            "'Gerar bordado'." % len(self.selecao))
            if depois:
                depois()

        self._rodar(lambda: core.preparar(self.caminho_img, p), fim, "Separando cores...")

    def gerar(self):
        if not self.caminho_img:
            messagebox.showinfo("Conversor", "Abra uma imagem primeiro.")
            return
        try:
            p = self._params()
        except tk.TclError:
            messagebox.showerror("Conversor", "Verifique os valores numéricos.")
            return
        if self.prep is None or self.prep_chave != self._chave(p):
            # parâmetros de separação mudaram: separa de novo e depois gera
            self.separar(depois=self.gerar)
            return
        if not any(s["bordar"] for s in self.selecao):
            messagebox.showinfo("Conversor", "Nenhuma cor está marcada para bordar.")
            return
        extra = {"espacamento_mm": p["espacamento_mm"], "ponto_mm": p["ponto_mm"]}
        nome = self.v["nome"].get() or "Bordado"
        sel = [dict(s) for s in self.selecao]
        self._rodar(lambda: core.gerar(self.prep, sel, self.pes_tmp, extra, nome),
                    lambda r: self._exibir(r, gerado=True), "Gerando pontos... aguarde.")

    def abrir_pes(self):
        c = filedialog.askopenfilename(title="Escolha o arquivo .pes", filetypes=[("Bordado Brother", "*.pes")])
        if not c:
            return
        try:
            res = core.ler_pes(c)
        except Exception as e:
            messagebox.showerror("Erro", "Não foi possível ler o arquivo:\n%s" % e)
            return
        self.lb_orig.configure(image="")
        self._exibir(res, gerado=False)
        self.status.set("Arquivo analisado: %s" % os.path.basename(c))

    def _exibir(self, res, gerado):
        info, blocos, ext = res
        cores = [b[0][1] for b in info["blocos"]]
        self.prev_img = core.renderizar(blocos, cores, ext, escala=0.6)
        self._mostrar(self.lb_prev, self.prev_img, "prev")
        minutos = info["pontos"] / 650.0
        self.resumo.set(
            "Nome: %s   |   PES v%s   |   %.1f × %.1f mm   |   %d pontos   |   %d trocas de cor   |   "
            "%d saltos (%d cortes)   |   tempo estimado ≈ %d min"
            % (info["nome"], info["versao"], info["largura_mm"], info["altura_mm"], info["pontos"],
               len(info["blocos"]) - 1, info["saltos"], info["cortes"], round(minutos)))
        self.tab.delete(*self.tab.get_children())
        for i, ((cod, rgb, nome), n) in enumerate(info["blocos"], 1):
            self.tab.insert("", "end", values=(i, hexrgb(rgb), "%s - %s" % (cod, nome), n))
        self.abas.select(1)
        self.bt_png.configure(state="normal")
        if gerado:
            self.pes_pronto = True
            self.bt_salvar.configure(state="normal")
            self.status.set("Bordado gerado. Confira a prévia e clique em 'Salvar .pes'.")
        else:
            self.bt_salvar.configure(state="disabled")

    def salvar(self):
        if not self.pes_pronto:
            return
        c = filedialog.asksaveasfilename(defaultextension=".pes",
                                         initialfile=(self.v["nome"].get() or "bordado") + ".pes",
                                         filetypes=[("Bordado Brother", "*.pes")])
        if c:
            shutil.copyfile(self.pes_tmp, c)
            self.status.set("Salvo em: %s" % c)

    def salvar_png(self):
        if self.prev_img is None:
            return
        c = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if c:
            self.prev_img.save(c)


if __name__ == "__main__":
    App().mainloop()
