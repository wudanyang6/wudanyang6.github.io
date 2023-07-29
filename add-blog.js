const util = require('util');
const child_process = require('child_process');
const exec = util.promisify(child_process.exec);

  
function getCreateTimeAsFileName() {
     const currentDate = new Date();

     const year = currentDate.getFullYear();
     const month = String(currentDate.getMonth() + 1).padStart(2, '0');
     const day = String(currentDate.getDate()).padStart(2, '0');

     return `${year}-${month}-${day}-`;
}

  

// execute command function

async function executeCommand() {
     const fileName = getCreateTimeAsFileName()+".md";
     const { stdout, stderr } = await exec('/opt/homebrew/bin/hugo new post/' +fileName,{cwd: app.fileManager.vault.adapter.basePath});
     console.log('stdout:', stdout);
     console.log('stderr:', stderr);
     if (stdout) {
         new Notice("New Blog Created["+fileName+"]")
     }else{
         new Notice("New Blog Create Faild. "+stderr)
     }
}

  

module.exports = async function(context, req) {
    await executeCommand();
}