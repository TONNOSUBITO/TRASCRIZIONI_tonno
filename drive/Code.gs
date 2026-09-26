// Web app Google Apps Script: riceve i .md dal bot e li salva nella cartella Drive "Trascrizioni".
const KEY = 'INCOLLA_QUI_LA_CHIAVE'; // la stessa di DRIVE_KEY su Vercel

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  if (d.key !== KEY) return ContentService.createTextOutput('forbidden');
  const it = DriveApp.getFoldersByName('Trascrizioni');
  const folder = it.hasNext() ? it.next() : DriveApp.createFolder('Trascrizioni');
  folder.createFile(d.name, d.content, 'text/markdown');
  return ContentService.createTextOutput('ok');
}
