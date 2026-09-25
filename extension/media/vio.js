// Vio, il polpetto viola di MyDevAgent: la stessa pixel art 14×8 del terminale (mydevagent/tui/mascot.py),
// disegnata in SVG. Cambia espressione con la modalità e mentre lavora muove i tentacoli.
(function () {
  const COLORS = {
    P: "#a855f7", // corpo
    D: "#581c87", // contorno e tentacoli
    L: "#d8b4fe", // riflesso
    K: "#1a0b2e", // occhi e bocca
    W: "#ffffff", // luce negli occhi
    C: "#f472b6", // guance e cuori
    Y: "#facc15", // occhi a stella
    B: "#67e8f9", // occhiali
    R: "#f43f5e", // errore
  };
  const HEAD = [".....DDDD.....", "...DDPPPPDD...", "..DPLPPPPPPD.."];
  const EYES = {
    open: [".DPPWKPPWKPPD.", ".DPPKKPPKKPPD."],
    happy: [".DPPKPPPPKPPD.", ".DPKPKPPKPKPD."],
    closed: [".DPPPPPPPPPPD.", ".DPKKKPPKKKPD."],
    look: [".DPPPWKPPWKPD.", ".DPPPKKPPKKPD."],
    glasses: [".DPBBBPPBBBPD.", ".DPBWKBBWKBPD."],
    stars: [".DPPYWPPYWPPD.", ".DPPYYPPYYPPD."],
    cross: [".DPRPRPPRPRPD.", ".DPPRPPPPRPPD."],
    hearts: [".DPCPCPPCPCPD.", ".DPPCPPPPCPPD."],
  };
  const MOUTHS = { smile: ".DPCPPKKPPCPD.", open: ".DPCPKKKKPCPD.", flat: ".DPCPPDDPPCPD." };
  const TENTACLES = [
    ["DPDPDPPPPDPDPD", "D.P.P.DD.P.P.D"],
    ["DPDPDPPPPDPDPD", ".D.P.PDDP.P.D."],
  ];
  const EXPRESSIONS = {
    ask: ["open", "smile"],
    "auto-edit": ["happy", "open"],
    plan: ["glasses", "flat"],
    auto: ["stars", "open"],
    chat: ["look", "smile"],
    think: ["look", "flat"],
    look: ["open", "flat"],
    blink: ["closed", "smile"],
    done: ["happy", "smile"],
    error: ["cross", "flat"],
    love: ["hearts", "smile"],
  };
  const SAYS = {
    ask: "Ti chiedo conferma prima di ogni modifica.",
    "auto-edit": "Modifico i file da sola, per i comandi ti chiedo.",
    plan: "Leggo e ti propongo un piano, senza toccare niente.",
    auto: "Faccio tutto da sola, dentro questa cartella.",
  };
  const PATS = ["Grazie! ♥", "Fusa da polpo in corso… ♥", "Otto tentacoli pronti a programmare! ♥", "Ancora, ancora! ♥"];

  function sprite(expression, frame) {
    const [eyes, mouth] = EXPRESSIONS[expression] || EXPRESSIONS.ask;
    return HEAD.concat(EYES[eyes], [MOUTHS[mouth]], TENTACLES[frame % TENTACLES.length]);
  }

  /** SVG di Vio: `size` è il lato di un pixel. */
  function svg(expression, frame, size) {
    const rows = sprite(expression, frame || 0);
    const px = size || 4;
    let rects = "";
    rows.forEach((row, y) => {
      for (let x = 0; x < row.length; x++) {
        const color = COLORS[row[x]];
        if (color) rects += `<rect x="${x}" y="${y}" width="1.02" height="1.02" fill="${color}"/>`;
      }
    });
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 8" width="${14 * px}" height="${8 * px}" ` +
      `shape-rendering="crispEdges" aria-hidden="true">${rects}</svg>`;
  }

  window.Vio = { svg, SAYS, PATS, EXPRESSIONS };
})();
