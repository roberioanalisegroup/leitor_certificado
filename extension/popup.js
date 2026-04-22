"use strict";

const HOST_NAME = "br.com.roberio.cert_reader";

let certificados = [];
let filtroTexto = "";
let selecionadoIdx = null;
let detalhesIdx = null;

// ---------------------------------------------------------------------------
// Elementos
// ---------------------------------------------------------------------------
const viewLista = document.getElementById("view-lista");
const viewDetalhes = document.getElementById("view-detalhes");

const tbody = document.getElementById("tbody");
const listaVazia = document.getElementById("lista-vazia");
const statusEl = document.getElementById("status");
const rodape = document.querySelector(".rodape");

const btnAtualizar = document.getElementById("btn-atualizar");
const btnExcluir = document.getElementById("btn-excluir");
const btnDetalhes = document.getElementById("btn-detalhes");
const btnExcluirDet = document.getElementById("btn-excluir-det");
const btnVoltar = document.getElementById("btn-voltar");
const btnFechar = document.getElementById("btn-fechar");

const btnMenu = document.getElementById("btn-menu");
const menuRepos = document.getElementById("menu-repos");
const checksRepos = menuRepos.querySelectorAll("input[type=checkbox]");

const busca = document.getElementById("busca");

const detTitular = document.getElementById("det-titular");
const detTipo = document.getElementById("det-tipo");
const detSituacao = document.getElementById("det-situacao");
const detCorpo = document.getElementById("det-corpo");

// ---------------------------------------------------------------------------
// Native Messaging
// ---------------------------------------------------------------------------
function sendNative(message) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendNativeMessage(HOST_NAME, message, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          resolve({
            ok: false,
            error: err.message || "Erro desconhecido no host nativo.",
            _nativeError: true,
          });
          return;
        }
        resolve(response);
      });
    } catch (exc) {
      resolve({ ok: false, error: String(exc), _nativeError: true });
    }
  });
}

// ---------------------------------------------------------------------------
// Formatadores
// ---------------------------------------------------------------------------
function fmtData(iso, apenasData = false) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const dia = String(d.getDate()).padStart(2, "0");
  const mes = String(d.getMonth() + 1).padStart(2, "0");
  const ano = d.getFullYear();
  if (apenasData) return `${dia}/${mes}/${ano}`;
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${dia}/${mes}/${ano} ${hh}:${mm}`;
}

function statusVencimento(cert) {
  if (!cert.data_vencimento || cert.dias_para_vencer === null) {
    return { texto: "Desconhecido", classe: "alerta" };
  }
  const dias = cert.dias_para_vencer;
  if (dias < 0) {
    return {
      texto: `Expirado há ${Math.abs(dias)} dia(s)`,
      classe: "expirado",
    };
  }
  if (dias <= 30) {
    return { texto: `Vence em ${dias} dia(s)`, classe: "alerta" };
  }
  return { texto: `Válido (${dias} dia(s))`, classe: "valido" };
}

function textoBuscavel(cert) {
  return [
    cert.titular_nome,
    cert.cpf,
    cert.cnpj,
    cert.empresa,
    cert.responsavel_nome,
    cert.email,
    cert.emissor,
    cert.tipo,
    cert.store,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

// ---------------------------------------------------------------------------
// Renderização da lista
// ---------------------------------------------------------------------------
function certificadosFiltrados() {
  if (!filtroTexto) return certificados.map((c, idx) => ({ cert: c, idx }));
  const termo = filtroTexto.toLowerCase().trim();
  const out = [];
  certificados.forEach((cert, idx) => {
    if (textoBuscavel(cert).includes(termo)) {
      out.push({ cert, idx });
    }
  });
  return out;
}

function renderLista() {
  tbody.innerHTML = "";
  const filtrados = certificadosFiltrados();

  if (!filtrados.length) {
    listaVazia.hidden = false;
    listaVazia.textContent = certificados.length
      ? "Nenhum certificado corresponde à busca."
      : "Nenhum certificado encontrado.";
  } else {
    listaVazia.hidden = true;
  }

  for (const { cert, idx } of filtrados) {
    const tr = document.createElement("tr");
    const st = statusVencimento(cert);
    tr.classList.add(st.classe);
    tr.dataset.idx = String(idx);
    if (idx === selecionadoIdx) tr.classList.add("selecionado");

    const tdNome = document.createElement("td");
    tdNome.textContent = cert.titular_nome || "(sem CN)";
    tdNome.title = cert.titular_nome || "";

    const tdData = document.createElement("td");
    tdData.className = "col-data";
    tdData.textContent = fmtData(cert.data_vencimento, true);

    tr.appendChild(tdNome);
    tr.appendChild(tdData);

    tr.addEventListener("click", () => selecionar(idx));
    tr.addEventListener("dblclick", () => {
      selecionar(idx);
      abrirDetalhes();
    });
    tbody.appendChild(tr);
  }

  atualizarBotoesAcao();
}

function selecionar(idx) {
  selecionadoIdx = idx;
  for (const tr of tbody.querySelectorAll("tr")) {
    tr.classList.toggle("selecionado", Number(tr.dataset.idx) === idx);
  }
  atualizarBotoesAcao();
}

function atualizarBotoesAcao() {
  const cert = selecionadoIdx !== null ? certificados[selecionadoIdx] : null;
  btnExcluir.disabled = !cert || !cert.id;
  btnDetalhes.disabled = !cert;
}

// ---------------------------------------------------------------------------
// Renderização dos detalhes
// ---------------------------------------------------------------------------
function abrirDetalhes() {
  if (selecionadoIdx === null) return;
  detalhesIdx = selecionadoIdx;
  const cert = certificados[detalhesIdx];
  if (!cert) return;

  detTitular.textContent = cert.titular_nome || "(sem CN)";

  detTipo.textContent = cert.tipo || "—";
  detTipo.className = "badge";

  const st = statusVencimento(cert);
  detSituacao.textContent = st.texto;
  detSituacao.className = `badge badge-${st.classe}`;

  detCorpo.innerHTML = "";

  const linhas = [];
  const push = (rotulo, valor) => {
    if (valor === undefined || valor === null || valor === "") return;
    linhas.push({ rotulo, valor: String(valor) });
  };

  push("Repositório", cert.store);
  push("CPF", cert.cpf);
  push("CNPJ", cert.cnpj);
  push("Empresa", cert.empresa);
  push("Responsável", cert.responsavel_nome);
  push("CPF do resp.", cert.responsavel_cpf);
  push("Data de nasc.", cert.data_nascimento);
  push("PIS/PASEP", cert.pis);
  push("RG", cert.rg);
  push("E-mail", cert.email);
  push("Emissão", fmtData(cert.data_emissao));
  push("Vencimento", fmtData(cert.data_vencimento));
  push("Emissor", cert.emissor || "-");
  push("Número de série", cert.numero_serie || "-");

  for (const l of linhas) {
    const linha = document.createElement("div");
    linha.className = "detalhes-linha";
    const r = document.createElement("span");
    r.className = "rotulo";
    r.textContent = l.rotulo;
    const v = document.createElement("span");
    v.className = "valor";
    v.textContent = l.valor;
    linha.appendChild(r);
    linha.appendChild(v);
    detCorpo.appendChild(linha);
  }
  for (const aviso of cert.warnings || []) {
    const linha = document.createElement("div");
    linha.className = "detalhes-linha aviso";
    const r = document.createElement("span");
    r.className = "rotulo";
    r.textContent = "Aviso";
    const v = document.createElement("span");
    v.className = "valor";
    v.textContent = aviso;
    linha.appendChild(r);
    linha.appendChild(v);
    detCorpo.appendChild(linha);
  }

  btnExcluirDet.disabled = !cert.id;

  viewLista.hidden = true;
  viewDetalhes.hidden = false;
  detCorpo.scrollTop = 0;
}

function voltarParaLista() {
  viewDetalhes.hidden = true;
  viewLista.hidden = false;
}

// ---------------------------------------------------------------------------
// Ações
// ---------------------------------------------------------------------------
function setStatus(msg, erro = false) {
  statusEl.textContent = msg;
  rodape.classList.toggle("erro", !!erro);
}

function reposSelecionados() {
  return [...checksRepos].filter((c) => c.checked).map((c) => c.dataset.store);
}

async function carregar() {
  const stores = reposSelecionados();
  if (!stores.length) {
    setStatus("Selecione ao menos um repositório.", true);
    certificados = [];
    selecionadoIdx = null;
    renderLista();
    return;
  }
  setStatus("Lendo certificados…");
  btnAtualizar.disabled = true;

  const resp = await sendNative({ action: "list", stores });
  btnAtualizar.disabled = false;

  if (!resp || !resp.ok) {
    mostrarErroHost(resp);
    return;
  }

  const todos = resp.certificados || [];
  certificados = todos.filter(
    (c) => c.tipo === "e-CPF" || c.tipo === "e-CNPJ"
  );
  selecionadoIdx = null;
  renderLista();

  const total = certificados.length;
  const pf = certificados.filter((c) => c.tipo === "e-CPF").length;
  const pj = certificados.filter((c) => c.tipo === "e-CNPJ").length;
  const ocultos = todos.length - total;
  const sufixo = ocultos > 0 ? ` (${ocultos} outro(s) oculto(s))` : "";
  setStatus(`${total} certificado(s) — e-CPF: ${pf} | e-CNPJ: ${pj}${sufixo}`);
}

function mostrarErroHost(resp) {
  const msg = resp && resp.error ? resp.error : "Sem resposta do host nativo.";
  setStatus("Erro: " + msg, true);

  if (document.querySelector(".alerta-instalacao")) return;
  const aviso = document.createElement("div");
  aviso.className = "alerta-instalacao";
  aviso.innerHTML = `
    <strong>O host nativo não respondeu.</strong><br />
    Verifique se <code>cert_host.exe</code> está instalado e registrado
    com o nome <code>${HOST_NAME}</code>. Rode <code>build.ps1</code> e
    depois <code>install.ps1</code> na pasta <code>native_host</code>.
    <br /><br />Mensagem: <code>${msg}</code>
  `;
  viewLista.insertBefore(aviso, viewLista.querySelector(".lista-wrapper"));
}

async function excluirAtual(idx) {
  if (idx === null || idx === undefined) return;
  const cert = certificados[idx];
  if (!cert || !cert.id) return;

  const titulo = cert.titular_nome || "(sem CN)";
  const msg =
    `Excluir o certificado abaixo do repositório "${cert.store}"?\n\n` +
    `${titulo}\n` +
    `Vencimento: ${fmtData(cert.data_vencimento)}\n\n` +
    "Esta operação não pode ser desfeita.";
  if (!confirm(msg)) return;

  setStatus("Excluindo certificado…");

  const resp = await sendNative({
    action: "delete",
    id: cert.id,
    store: cert.store,
  });

  if (!resp || !resp.ok) {
    setStatus("Erro ao excluir: " + (resp && resp.error ? resp.error : "?"), true);
    alert("Não foi possível excluir:\n\n" + (resp && resp.error ? resp.error : ""));
    return;
  }

  setStatus(`Certificado "${titulo}" removido.`);
  if (!viewDetalhes.hidden) voltarParaLista();
  await carregar();
}

// ---------------------------------------------------------------------------
// Menu dropdown (3 pontinhos) – repositórios
// ---------------------------------------------------------------------------
function toggleMenu(force) {
  const abrir =
    typeof force === "boolean" ? force : menuRepos.hidden;
  menuRepos.hidden = !abrir;
}

document.addEventListener("click", (ev) => {
  if (menuRepos.hidden) return;
  if (
    ev.target === btnMenu ||
    btnMenu.contains(ev.target) ||
    menuRepos.contains(ev.target)
  ) {
    return;
  }
  toggleMenu(false);
});

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape") {
    if (!menuRepos.hidden) {
      toggleMenu(false);
      return;
    }
    if (!viewDetalhes.hidden) {
      voltarParaLista();
    }
  }
});

// ---------------------------------------------------------------------------
// Bindings
// ---------------------------------------------------------------------------
btnAtualizar.addEventListener("click", carregar);
btnExcluir.addEventListener("click", () => excluirAtual(selecionadoIdx));
btnExcluirDet.addEventListener("click", () => excluirAtual(detalhesIdx));
btnDetalhes.addEventListener("click", abrirDetalhes);
btnVoltar.addEventListener("click", voltarParaLista);
btnFechar.addEventListener("click", () => window.close());
btnMenu.addEventListener("click", (ev) => {
  ev.stopPropagation();
  toggleMenu();
});

for (const cb of checksRepos) {
  cb.addEventListener("change", carregar);
}

busca.addEventListener("input", () => {
  filtroTexto = busca.value || "";
  renderLista();
});

document.addEventListener("DOMContentLoaded", carregar);
