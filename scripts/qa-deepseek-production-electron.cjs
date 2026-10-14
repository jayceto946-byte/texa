const { _electron } = require('playwright');
const {mkdirSync,writeFileSync} = require('node:fs');
const {resolve} = require('node:path');
const out=resolve('docs/qa/evidence/deepseek-production/electron'); mkdirSync(out,{recursive:true});
const userData='/private/tmp/texa-deepseek-production-electron-'+Date.now(); mkdirSync(userData,{recursive:true});
writeFileSync(resolve(userData,'setup-complete.json'),JSON.stringify({version:3,complete:true}));
const result={environment:'macOS Electron; production adapter with Mock HTTP provider; not paid acceptance',checks:[],errors:[],sse:[]};
(async()=>{
 let app,page;
 try {
  app=await _electron.launch({executablePath:resolve('desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron'),args:[resolve('desktop')],env:{...process.env,KAOYAN_USER_DATA_DIR:userData,KAOYAN_SKIP_BACKEND:'1',KAOYAN_BACKEND_URL:'http://127.0.0.1:18041',KAOYAN_FRONTEND_DEV_URL:'http://127.0.0.1:18041'}});
  page=await app.firstWindow(); page.setDefaultTimeout(20000);
  page.on('pageerror',e=>result.errors.push(String(e)));
  page.on('response',async response=>{if(response.url().endsWith('/api/chat/stream')){try{const text=await response.text();if(text.includes('PRIVATE_REASONING_NEVER_EXPORT'))result.errors.push('private SSE leak');result.sse.push(text);}catch{}}});
  await page.locator('.composer-textarea').waitFor();
  await page.getByRole('button',{name:'设置',exact:true}).click();
  await page.getByRole('button',{name:'模型连接',exact:true}).waitFor(); await page.getByRole('button',{name:'模型连接',exact:true}).click();
  await page.getByRole('combobox',{name:'切换并应用模型方案'}).waitFor();
  if(!(await page.getByRole('combobox',{name:'切换并应用模型方案'}).innerText()).includes('QA Qwen 默认')){await page.getByRole('combobox',{name:'切换并应用模型方案'}).click();await page.getByRole('option',{name:/QA Qwen 默认/}).click();await page.getByRole('combobox',{name:'回答模型 Model'}).filter({hasText:'Qwen 3.7 Plus'}).waitFor();}
  result.checks.push('Qwen default profile');
  await page.getByRole('combobox',{name:'切换并应用模型方案'}).click();
  await page.getByRole('option',{name:/QA Flash 可选/}).click();
  await page.getByRole('combobox',{name:'回答模型'}).filter({hasText:'DeepSeek V4.1 Flash'}).waitFor();
  result.checks.push('existing model selection switches to registered Flash');
  await page.screenshot({path:resolve(out,'flash-selection.png')});
  await page.getByRole('button',{name:'关闭设置',exact:true}).click();
  const submit=async text=>{await page.locator('.composer-textarea').fill(text);await page.getByRole('button',{name:'发送问题',exact:true}).click();};
  await submit('计算 2^10');
  await page.getByText('结果是 1024。',{exact:true}).last().waitFor();
  await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
  result.checks.push('Flash actual LangChain adapter multi-tool SQL SSE final');
  for(const [width,height] of [[1280,820],[1024,768],[760,820]]){await page.setViewportSize({width,height});await page.screenshot({path:resolve(out,`${width}-final.png`)});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))throw Error(`overflow ${width}`);}
  await page.setViewportSize({width:1280,height:820});
  if(await page.getByRole('button',{name:'展开侧栏',exact:true}).isVisible())await page.getByRole('button',{name:'展开侧栏',exact:true}).click();
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await submit('简要说明如何复习');
  await page.getByText('建议先梳理概念，再用例题检查理解。',{exact:true}).last().waitFor();
  await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
  await page.screenshot({path:resolve(out,'plain-native-answer.png')});
  result.checks.push('ordinary teaching uses the same native SQL Runtime with zero model tools');
  await page.getByRole('button',{name:'新会话',exact:true}).click();
  await submit('计算 7');
  await page.locator('.execution-title').filter({hasText:'正在继续解答'}).last().waitFor();
  await page.getByRole('button',{name:'停止生成',exact:true}).click();
  await page.getByRole('button',{name:'发送问题',exact:true}).waitFor();
  await page.reload();await page.locator('.composer-textarea').waitFor();
  await page.locator('.context-session-row').filter({hasText:'计算 7'}).first().click();
  result.checks.push('cancel acknowledged and session reload works');
  await page.getByRole('button',{name:'继续本次解答',exact:true}).waitFor();
  await page.getByRole('button',{name:'继续本次解答',exact:true}).click();
  await page.getByText('详细信息',{exact:true}).last().click();
  await page.getByText('本次模型续答状态已丢失，请重新发起问题；已执行工具记录保留。',{exact:false}).last().waitFor();
  result.checks.push('resume explicitly fails on lost private state; no replay');
  await page.screenshot({path:resolve(out,'resume-failure.png')});
  const body=await page.locator('body').innerText();if(/PRIVATE_REASONING_NEVER_EXPORT|reasoning_content|qa-fake-key/.test(body))throw Error('private UI leak');

 }catch(e){result.errors.push(String(e));process.exitCode=1;if(page)await page.screenshot({path:resolve(out,'error.png')});}
 finally{await app?.close();writeFileSync(resolve(out,'results.json'),JSON.stringify(result,null,2));}
})();
