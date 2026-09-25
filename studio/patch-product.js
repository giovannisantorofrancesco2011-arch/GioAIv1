// Trasforma il product.json di VSCodium in quello di MyDevAgent Studio (lo usa studio/build.ps1).
//   node patch-product.js <percorso di product.json>
const fs = require("fs");

const file = process.argv[2];
const product = JSON.parse(fs.readFileSync(file, "utf8"));
Object.assign(product, {
  nameShort: "MyDevAgent Studio",
  nameLong: "MyDevAgent Studio",
  dataFolderName: ".mydevagent-studio", // estensioni e impostazioni separate da VSCodium
  serverDataFolderName: ".mydevagent-studio-server",
  urlProtocol: "mydevagent-studio",
  win32MutexName: "mydevagentstudio",
  win32AppUserModelId: "MyDevAgent.Studio", // icona separata da VSCodium sulla barra delle applicazioni
  win32DirName: "MyDevAgent Studio",
  win32NameVersion: "MyDevAgent Studio",
  win32RegValueName: "MyDevAgentStudio",
  win32ShellNameShort: "MyDevAgent Studio",
});
delete product.updateUrl; // niente aggiornamenti di VSCodium al posto di Studio
delete product.checksums; // cambiamo icone e filigrana: senza, VSCodium direbbe «installazione danneggiata»
fs.writeFileSync(file, JSON.stringify(product, null, "\t") + "\n");
console.log(`product.json: ${product.nameLong} (VSCodium ${product.version})`);
