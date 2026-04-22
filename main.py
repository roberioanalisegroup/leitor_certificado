"""
Leitor de Certificados Digitais – Windows
=========================================

Aplicativo gráfico que lê os certificados instalados no repositório do
Windows e exibe um resumo amigável, com foco em certificados ICP-Brasil
(e-CPF e e-CNPJ).

Execução:
    python main.py
"""

from __future__ import annotations

import csv
import datetime
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from cert_reader import CertificadoInfo, listar_certificados, remover_certificado


STORES_DISPONIVEIS = [
    ("MY", "Pessoal (e-CPF / e-CNPJ)"),
    ("CA", "Autoridades Intermediárias"),
    ("ROOT", "Autoridades Raiz Confiáveis"),
]


def _fmt_data(d: datetime.datetime | None) -> str:
    if not d:
        return "-"
    # Converte para hora local só para exibição amigável.
    local = d.astimezone()
    return local.strftime("%d/%m/%Y %H:%M")


def _status_vencimento(cert: CertificadoInfo) -> tuple[str, str]:
    """Retorna (texto, tag_cor) para a coluna de status."""
    if not cert.data_vencimento:
        return ("Desconhecido", "alerta")
    dias = cert.dias_para_vencer
    if dias is None:
        return ("Desconhecido", "alerta")
    if dias < 0:
        return (f"Expirado há {abs(dias)} dia(s)", "expirado")
    if dias <= 30:
        return (f"Vence em {dias} dia(s)", "alerta")
    return (f"Válido ({dias} dia(s))", "valido")


class LeitorCertificadosApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Leitor de Certificados Digitais – Windows")
        self.geometry("1100x650")
        self.minsize(960, 560)

        self.certificados: list[CertificadoInfo] = []

        self._build_style()
        self._build_layout()
        self.after(200, self.carregar_certificados)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista" if sys.platform == "win32" else "clam")
        except tk.TclError:
            style.theme_use("clam")
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        style.configure("TButton", padding=6)
        style.configure(
            "Perigo.TButton",
            padding=6,
            foreground="#991b1b",
        )
        style.map(
            "Perigo.TButton",
            foreground=[("disabled", "#9ca3af"), ("active", "#7f1d1d")],
        )
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("Titulo.TLabel", font=("Segoe UI Semibold", 14))
        style.configure("Campo.TLabel", font=("Segoe UI Semibold", 10))

    def _build_layout(self) -> None:
        # Cabeçalho
        topo = ttk.Frame(self, padding=(12, 10))
        topo.pack(fill="x")

        ttk.Label(
            topo,
            text="Certificados instalados no Windows",
            style="Titulo.TLabel",
        ).pack(side="left")

        ttk.Button(topo, text="Atualizar", command=self.carregar_certificados).pack(
            side="right"
        )
        ttk.Button(topo, text="Exportar CSV", command=self.exportar_csv).pack(
            side="right", padx=6
        )
        self.btn_excluir = ttk.Button(
            topo,
            text="Excluir",
            style="Perigo.TButton",
            command=self.excluir_selecionado,
            state="disabled",
        )
        self.btn_excluir.pack(side="right", padx=6)

        # Seletor de repositório
        filtros = ttk.Frame(self, padding=(12, 0))
        filtros.pack(fill="x")
        ttk.Label(filtros, text="Repositórios:").pack(side="left")
        self.store_vars: dict[str, tk.BooleanVar] = {}
        for code, label in STORES_DISPONIVEIS:
            var = tk.BooleanVar(value=(code == "MY"))
            self.store_vars[code] = var
            ttk.Checkbutton(
                filtros,
                text=label,
                variable=var,
                command=self.carregar_certificados,
            ).pack(side="left", padx=6)

        # Painel principal com lista + detalhes
        painel = ttk.Panedwindow(self, orient="horizontal")
        painel.pack(fill="both", expand=True, padx=12, pady=10)

        # ---- Lista de certificados ----
        frame_lista = ttk.Frame(painel)
        painel.add(frame_lista, weight=3)

        colunas = ("titular", "vencimento")
        self.tree = ttk.Treeview(
            frame_lista, columns=colunas, show="headings", selectmode="browse"
        )
        titulos = {
            "titular": ("Nome do certificado", 420),
            "vencimento": ("Data de validade", 160),
        }
        for col, (txt, w) in titulos.items():
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w")

        self.tree.tag_configure("valido", foreground="#14532d")
        self.tree.tag_configure("alerta", foreground="#92400e")
        self.tree.tag_configure(
            "expirado", foreground="#ffffff", background="#dc2626"
        )

        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ---- Painel de detalhes ----
        frame_det = ttk.Frame(painel, padding=10)
        painel.add(frame_det, weight=2)

        ttk.Label(frame_det, text="Detalhes", style="Titulo.TLabel").pack(anchor="w")
        ttk.Separator(frame_det).pack(fill="x", pady=6)

        self.texto_detalhes = tk.Text(
            frame_det,
            wrap="word",
            font=("Consolas", 10),
            relief="flat",
            background="#f8fafc",
            padx=8,
            pady=8,
        )
        self.texto_detalhes.pack(fill="both", expand=True)
        self.texto_detalhes.configure(state="disabled")

        # Rodapé
        self.status_var = tk.StringVar(value="Pronto.")
        rodape = ttk.Frame(self, padding=(12, 6))
        rodape.pack(fill="x")
        ttk.Label(rodape, textvariable=self.status_var).pack(side="left")

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def carregar_certificados(self) -> None:
        stores = tuple(code for code, var in self.store_vars.items() if var.get())
        if not stores:
            messagebox.showwarning(
                "Seleção vazia",
                "Selecione ao menos um repositório para listar os certificados.",
            )
            return

        self.status_var.set("Lendo certificados…")
        self.update_idletasks()

        try:
            self.certificados = listar_certificados(stores)
        except Exception as exc:  # pragma: no cover - defensivo
            messagebox.showerror(
                "Erro",
                f"Falha ao ler os certificados do Windows:\n\n{exc}",
            )
            self.status_var.set("Erro ao ler certificados.")
            return

        self._popular_lista()
        total = len(self.certificados)
        pf = sum(1 for c in self.certificados if c.tipo == "e-CPF")
        pj = sum(1 for c in self.certificados if c.tipo == "e-CNPJ")
        self.status_var.set(
            f"{total} certificado(s) encontrado(s) — e-CPF: {pf} | e-CNPJ: {pj}"
        )

    def _popular_lista(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        for idx, cert in enumerate(self.certificados):
            _, tag = _status_vencimento(cert)
            venc = _fmt_data(cert.data_vencimento).split(" ")[0]  # só data na lista
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    cert.titular_nome or "(sem CN)",
                    venc,
                ),
                tags=(tag,),
            )

        self.btn_excluir.configure(state="disabled")

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            self.btn_excluir.configure(state="disabled")
            return
        idx = int(sel[0])
        cert = self.certificados[idx]
        self._mostrar_detalhes(cert)
        self.btn_excluir.configure(
            state=("normal" if cert.raw_der else "disabled")
        )

    def excluir_selecionado(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        cert = self.certificados[idx]
        if not cert.raw_der:
            messagebox.showwarning(
                "Exclusão indisponível",
                "Não foi possível identificar os dados brutos deste "
                "certificado para exclusão.",
            )
            return

        titulo = cert.titular_nome or "(sem CN)"
        confirmar = messagebox.askyesno(
            "Excluir certificado",
            (
                f"Tem certeza que deseja excluir o certificado abaixo do "
                f"repositório '{cert.store}'?\n\n"
                f"{titulo}\n"
                f"Vencimento: {_fmt_data(cert.data_vencimento)}\n\n"
                "Esta operação não pode ser desfeita."
            ),
            icon="warning",
            default="no",
        )
        if not confirmar:
            return

        try:
            remover_certificado(cert.raw_der, cert.store)
        except Exception as exc:
            messagebox.showerror(
                "Erro ao excluir",
                f"Não foi possível excluir o certificado:\n\n{exc}",
            )
            return

        messagebox.showinfo(
            "Certificado excluído",
            f"O certificado '{titulo}' foi removido do repositório.",
        )
        self.texto_detalhes.configure(state="normal")
        self.texto_detalhes.delete("1.0", "end")
        self.texto_detalhes.configure(state="disabled")
        self.carregar_certificados()

    def _mostrar_detalhes(self, cert: CertificadoInfo) -> None:
        linhas: list[tuple[str, str]] = []
        linhas.append(("Repositório", cert.store))
        linhas.append(("Tipo", cert.tipo or "-"))
        linhas.append(("Titular (CN)", cert.titular_nome or "-"))
        if cert.cpf:
            linhas.append(("CPF", cert.cpf))
        if cert.cnpj:
            linhas.append(("CNPJ", cert.cnpj))
        if cert.empresa:
            linhas.append(("Empresa", cert.empresa))
        if cert.responsavel_nome:
            linhas.append(("Responsável", cert.responsavel_nome))
        if cert.responsavel_cpf:
            linhas.append(("CPF do responsável", cert.responsavel_cpf))
        if cert.data_nascimento:
            linhas.append(("Data de nascimento", cert.data_nascimento))
        if cert.pis:
            linhas.append(("PIS/PASEP", cert.pis))
        if cert.rg:
            linhas.append(("RG", cert.rg))
        if cert.email:
            linhas.append(("E-mail", cert.email))

        linhas.append(("Data de emissão", _fmt_data(cert.data_emissao)))
        linhas.append(("Data de vencimento", _fmt_data(cert.data_vencimento)))
        status_txt, _ = _status_vencimento(cert)
        linhas.append(("Situação", status_txt))
        linhas.append(("Emissor", cert.emissor or "-"))
        linhas.append(("Número de série", cert.numero_serie or "-"))
        for aviso in cert.warnings:
            linhas.append(("Aviso", aviso))

        largura = max(len(rotulo) for rotulo, _ in linhas) + 2
        texto = "\n".join(f"{rotulo.ljust(largura)}: {valor}" for rotulo, valor in linhas)

        self.texto_detalhes.configure(state="normal")
        self.texto_detalhes.delete("1.0", "end")
        self.texto_detalhes.insert("1.0", texto)
        self.texto_detalhes.configure(state="disabled")

    def exportar_csv(self) -> None:
        if not self.certificados:
            messagebox.showinfo("Nada a exportar", "Nenhum certificado carregado.")
            return

        caminho = filedialog.asksaveasfilename(
            title="Salvar resumo dos certificados",
            defaultextension=".csv",
            filetypes=[("CSV (separado por ;)", "*.csv"), ("Todos os arquivos", "*.*")],
            initialfile="certificados.csv",
        )
        if not caminho:
            return

        try:
            with open(caminho, "w", encoding="utf-8-sig", newline="") as fp:
                writer = csv.writer(fp, delimiter=";")
                writer.writerow(
                    [
                        "Repositório",
                        "Tipo",
                        "Titular",
                        "CPF",
                        "CNPJ",
                        "Empresa",
                        "Responsável",
                        "CPF do responsável",
                        "E-mail",
                        "Data de emissão",
                        "Data de vencimento",
                        "Situação",
                        "Emissor",
                        "Número de série",
                    ]
                )
                for cert in self.certificados:
                    situacao, _ = _status_vencimento(cert)
                    writer.writerow(
                        [
                            cert.store,
                            cert.tipo,
                            cert.titular_nome,
                            cert.cpf,
                            cert.cnpj,
                            cert.empresa,
                            cert.responsavel_nome,
                            cert.responsavel_cpf,
                            cert.email,
                            _fmt_data(cert.data_emissao),
                            _fmt_data(cert.data_vencimento),
                            situacao,
                            cert.emissor,
                            cert.numero_serie,
                        ]
                    )
        except OSError as exc:
            messagebox.showerror("Erro", f"Não foi possível gravar o arquivo:\n{exc}")
            return

        messagebox.showinfo("Exportação concluída", f"Arquivo salvo em:\n{caminho}")


def main() -> None:
    if sys.platform != "win32":
        print(
            "Este aplicativo lê o repositório nativo de certificados do Windows "
            "(crypt32.dll) e só funciona no Windows."
        )
        sys.exit(1)
    app = LeitorCertificadosApp()
    app.mainloop()


if __name__ == "__main__":
    main()
