'use strict';
const data = window.RESEARCH_SNAPSHOT;
const app = document.getElementById('app');
const dialog = document.getElementById('detail-dialog');
const icon = name => window.MINER_ICONS[name] || '';
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const examples = {
  note: '我想找一些面向学生的笔记工具机会，类似 GoodNotes，重点关注整理和复习。',
  partial: '我想做一个在线客服 Agent，看看客服工作中还有哪些没有被解决的痛点。'
};
const names = {note: '笔记工具研究', partial: '客服 Agent 研究'};
const state = {scenario:'note', page:0, approved:false, completed:0, selectedStage:0, playing:false, keywords:[], query:examples.note, showKeywords:false};
let playback;
let toastTimeout;
let dialogFocus;
let selectedCard = 0;
const translations = [
  {
    title:'笔记同步冲突与安全恢复', icon:'ShieldCheck', user:'跨设备、跨云服务使用 Logseq 的笔记用户',
    pain:'多端同步可能让旧版本覆盖新编辑。出现冲突后，用户难以确认哪些内容丢失、应该恢复哪个版本。',
    workaround:'关闭其他设备上的 Logseq、重试同步、手动清理备份文件，再从历史版本中找回内容。',
    mvp:'在同步前保留快照，检测冲突并展示版本差异，让用户选择恢复或保留两个版本。',
    next:'访谈确认冲突频率与恢复成本',
    validation:['访谈 10–15 位经历过同步丢失的用户，确认触发场景、发生频率和恢复成本。','用冲突时间线与恢复原型验证：用户是否能正确识别并恢复所需版本。','在本地模拟并发编辑，测量恢复成功率；再验证加密历史记录的付费意愿。'],
    risk:'需要与 Logseq 文件格式、同步服务深度集成；笔记隐私和恢复安全也会影响用户信任。',
    assumption:'样本尚不能证明同步问题的普遍程度，也不能证明用户愿意付费。',
    commercial:'免费提供基础保护，付费提供加密版本历史、更长保留期和跨设备恢复。'
  },
  {
    title:'大型笔记库性能诊断', icon:'Activity', user:'使用大型图谱、超长页面或多个插件的 Logseq 用户',
    pain:'随着笔记规模增大，加载、索引、输入和滚动可能明显变慢，甚至出现崩溃，用户很难定位原因。',
    workaround:'拆分大页面、禁用插件、等待索引、强制退出或回退版本，逐项尝试。',
    mvp:'提供本地性能检查，定位大页面、索引任务和插件负担，并给出安全模式与清理建议。',
    next:'验证诊断建议是否能缓解卡顿',
    validation:['招募使用大型图谱的用户，定义图谱规模门槛并收集匿名性能记录。','用诊断报告原型测试用户能否理解问题来源和建议操作。','验证建议是否能在不丢失内容的前提下改善启动和编辑速度。'],
    risk:'外部工具可能无法充分访问渲染器或插件运行时。用户也可能期待直接修复，而不仅是诊断报告。',
    assumption:'多个平台出现相关 Issue，但不能据此推算全部用户中的发生比例。',
    commercial:'面向重度用户和团队提供付费诊断，或为插件开发者提供质量监测。'
  },
  {
    title:'Android 最小权限笔记访问', icon:'Smartphone', user:'使用大型或外部同步图谱、关注隐私的 Android 用户',
    pain:'大型图谱可能加载崩溃；应用请求广泛文件权限，部分存储服务也无法稳定选取。',
    workaround:'回退版本、缩小图谱、授予广泛文件访问权限，或更换存储服务。',
    mvp:'探索支持分区存储的图谱访问方案，结合增量加载、权限审计和崩溃后的安全启动。',
    next:'继续收集权限与存储兼容证据',
    validation:['访谈使用 Nextcloud 或大型图谱的 Android 用户，确认具体限制。','以最小读写权限制作窄范围原型，测量启动耗时和内存占用。','验证用户是否愿意为可靠访问及更小权限范围更换方案或付费。'],
    risk:'不同 Android 版本和存储服务行为差异较大，缺乏官方集成时兼容性难以保证。',
    assumption:'加载、权限和存储兼容是相邻问题；是否适合由同一产品解决，还需要补充验证。',
    commercial:'提供付费 Android 配套应用，或订阅制存储连接器与加密移动同步。'
  }
];
function tag(text, color='green') { return `<span class="tag ${color}">${text}</span>`; }
function button(text, action, symbol='ArrowRight', primary=false) { return `<button class="button ${primary?'primary':''}" data-action="${action}">${text}${icon(symbol)}</button>`; }
function iconButton(name, action, title) { return `<button class="icon-button" data-action="${action}" title="${title}" aria-label="${title}">${icon(name)}</button>`; }
function notify(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('visible');
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove('visible'), 4000);
}
function isDraft() { return state.query !== examples[state.scenario] || state.keywords.length > 0; }
function render() {
  app.innerHTML = `
    <header class="header">
      <a class="brand" href="#" data-action="home"><span class="brand-mark">${icon('ScanSearch')}</span><span><span class="brand-name">Opportunity Miner</span><span class="brand-sub" style="display:block">机会研究工作台</span></span></a>
      <div class="header-right"><span class="replay-tag">${icon('Clock')}历史案例回放</span>${iconButton('CircleHelp','about','查看案例与交互说明')}</div>
    </header>
    <div class="workspace">
      <aside class="sidebar"><div class="nav-label">本次研究</div><nav class="steps" aria-label="研究步骤">
        ${['研究方向','研究过程','研究结果'].map((label,index) => `<button class="nav-step ${state.page===index?'active':''}" data-page="${index}" ${index>0&&!state.approved||index===2&&state.completed<5?'disabled':''} ${state.page===index?'aria-current="step"':''}><span class="step-number">${index<state.page?icon('Check'):`0${index+1}`}</span>${label}</button>`).join('')}
      </nav><div class="sidebar-note"><strong>${icon('GitBranch')} GitHub 公开证据</strong>方向确认 · 证据研究 · 机会假设<br><br>LOCAL PROTOTYPE / V0.1</div></aside>
      <main class="main"><div class="main-inner">
        <div class="toolbar"><div class="breadcrumb">研究工作台 ${icon('ChevronRight')} <span>${names[state.scenario]}</span></div><div class="case-picker"><label for="case-picker">案例</label><select id="case-picker"><option value="note" ${state.scenario==='note'?'selected':''}>笔记工具 · 有研究结果</option><option value="partial" ${state.scenario==='partial'?'selected':''}>客服 Agent · 证据不足</option></select></div></div>
        ${state.page===0?renderInput():state.page===1?renderProcess():renderResults()}
        <footer class="footer"><span>Mini Opportunity Miner</span><button class="text-button small" data-action="case-details">案例记录 ${icon('FileText')}</button></footer>
      </div></main>
    </div>`;
}
function renderInput() {
  const note = state.scenario==='note';
  return `<div class="page-heading"><div class="eyebrow">01 / 研究方向</div><h1>从一个想探索的方向开始</h1><p>确认研究边界，剩下的交给 Agent。</p></div>
    <div class="intro-grid"><section class="input-side" aria-label="研究需求">
      <div class="section-heading">${icon('NotebookPen')}你的研究需求</div>
      <div class="label-row"><label for="research-query">想探索什么机会？</label><span class="meta-label">原型输入示例</span></div>
      <textarea id="research-query" maxlength="1200">${escapeHtml(state.query)}</textarea>
      <p class="input-caption">用你自己的话描述方向即可。</p>
      <div class="keyword-section"><button class="text-button" data-action="toggle-keywords" aria-expanded="${state.showKeywords}">${icon('Plus')}补充关键词 <span class="muted">· 可选</span></button>
        ${state.showKeywords?`<form class="keyword-form" id="keyword-form"><label class="visually-hidden" for="keyword-input">重要关键词</label><input id="keyword-input" maxlength="40" placeholder="例如：手写笔记、跨设备同步"><button class="icon-button" type="submit" title="添加关键词" aria-label="添加关键词">${icon('Plus')}</button></form>`:''}
        <div class="chips">${state.keywords.map((word,index)=>`<span class="chip">${escapeHtml(word)}<button data-remove-keyword="${index}" aria-label="删除关键词 ${escapeHtml(word)}" title="删除关键词">${icon('X')}</button></span>`).join('')}</div>
      </div>
      <div id="draft-note" class="draft-note" ${isDraft()?'':'hidden'}>已保留演示草稿。继续后仍回放所选历史案例，编辑不会发起新检索。</div>
      <details class="history-details"><summary>查看本案例的历史输入</summary><p>${note?escapeHtml(data.note.originalQuery):'I am a freelance software engineer looking to develop an online customer service agent, and I’d like to identify any remaining pain points that haven’t yet been addressed.'}</p><p class="muted">页面中的简短中文输入是原型示例，历史结果来自原始运行记录。</p></details>
    </section><section class="boundary-side" aria-label="研究边界">
      <div class="boundary-title"><h2>本次回放的研究边界</h2>${tag('待你确认','blue')}</div>
      <dl class="boundary-list">
        <div><dt>目标人群</dt><dd>${note?'学生及笔记工具使用者':'客服团队与在线服务业务'}</dd></div>
        <div><dt>探索领域</dt><dd>${note?'类似 GoodNotes 的笔记应用':'在线客服 Agent'}</dd></div>
        <div><dt>关注场景</dt><dd>${note?'笔记整理、搜索、复习、跨设备使用':'客服回复、人工接管、工作流衔接'}</dd></div>
        <div><dt>期望产出</dt><dd>有 Issue 来源支持、值得继续验证的工具或产品机会</dd></div>
      </dl>
      <div class="boundary-note">${icon('Search')}<span>证据范围：GitHub 开源项目中的公开 Issue。研究结果会标明实际覆盖的人群与场景。</span></div>
    </section></div>
    <div class="actions"><p>演示交互 · 确认后开始播放所选案例</p><button id="approve-button" class="button primary" data-action="approve" ${state.query.trim()?'':'disabled'}>确认并开始研究${icon('ArrowRight')}</button></div>`;
}
function stageNames() {
  return state.scenario==='note' ? [
    ['研究边界已确认','确定方向与检索边界'],['证据来源已确认','人工确认 Logseq 与 Joplin'],['公开 Issue 已采集','50 条有效 Issue 进入分析'],['痛点归纳完成','整理问题、替代方案与风险'],['研究结果已生成','3 张待验证的机会卡']
  ] : [
    ['研究方向','在线客服与工作流痛点'],['候选仓库检索','3 次仓库查询'],['仓库内 Issue 检索','10 次查询，结果为 0'],['补充检索与扩展','3 次全局查询、8 次扩展查询'],['证据不足，停止生成','没有形成可用的来源候选']
  ];
}
function renderProcess() {
  const done = state.completed===5;
  const partial = state.scenario==='partial';
  const stages = stageNames();
  return `<div class="page-heading"><div class="eyebrow">02 / 研究过程</div><h1>${done?(partial?'这次研究停在了证据环节':'每一步判断，都有依据'):'沿着证据，逐步接近机会'}</h1><p>${partial?'客服 Agent · 独立历史案例':'笔记工具 · 历史研究记录'}</p></div>
    <div class="flow-summary ${done&&partial?'warn':''}"><div role="status" aria-live="polite"><strong>${done?(partial?'证据不足 · 暂不生成机会卡':'研究完成 · 3 个机会假设'):state.playing?'正在回放历史研究过程':'回放已暂停'}</strong><p>${done?(partial?'未找到足够相关的 Issue，不能据此判断该领域没有需求。':'证据与机会卡来自已保存的同一次 run。'):`已回放 ${state.completed} / 5 个阶段 · 非实时检索`}</p></div><div class="flow-tools">${done?iconButton('RotateCcw','replay','重新回放'):iconButton(state.playing?'Pause':'Play','toggle-play',state.playing?'暂停回放':'继续回放')}${done?'':iconButton('SkipForward','skip','直接查看完整记录')}</div></div>
    <div class="progress-track" aria-hidden="true"><span style="width:${state.completed*20}%"></span></div>
    <div class="process-grid"><nav class="timeline" aria-label="研究阶段">${stages.map(([title,desc],index)=>`<button class="stage-button ${index<state.completed?'done':''} ${state.selectedStage===index?'selected':''}" data-stage="${index}" ${index>=state.completed?'disabled':''}><span class="stage-dot">${index<state.completed?icon('Check'):index+1}</span><span class="stage-text"><strong>${title}</strong><p>${desc}</p></span>${state.selectedStage===index?icon('ChevronRight'):''}</button>`).join('')}</nav><section class="detail-surface" aria-label="阶段依据">${renderStage()}</section></div>
    <div class="actions">${button('返回研究方向','input','ArrowLeft')}<button class="button primary" data-action="results" ${done?'':'disabled'}>${partial?'查看证据缺口':'查看 3 张机会卡'}${icon('ArrowRight')}</button></div>`;
}
function renderStage() {
  const stage = state.selectedStage;
  if (state.scenario==='partial') {
    const headings = ['研究对象','仓库召回','仓库内检索','补充检索','为什么没有机会卡'];
    const copy = ['该历史案例探索在线客服 Agent 的未解决痛点。当前页面的确认操作属于演示交互。','仓库查询成功返回结果，但“找到仓库”并不等于找到适合作为证据源的产品。','前两个候选仓库占用了 10 次 Issue 查询，均未找到匹配记录。','历史记录包含 3 次全局 Issue 查询和 8 次扩展查询，返回数量均为 0。','来源候选数为 0，无法支持后续机会生成。停在此处可以避免把缺乏证据的推测包装成研究结论。'];
    return `<div class="surface-head"><h2>${headings[stage]}</h2>${tag('历史记录','amber')}</div><p class="small muted">${copy[stage]}</p>${stage===1||stage===2?`<div class="source-row"><span class="source-monogram">I</span><div class="source-copy"><a href="https://github.com/Isaac24Karat/ai-booking-optimization-system" target="_blank" rel="noopener noreferrer">Isaac24Karat / ai-booking-optimization-system ${icon('ExternalLink')}</a><small>历史候选 · 查询结果 0</small></div></div><div class="source-row"><span class="source-monogram">A</span><div class="source-copy"><a href="https://github.com/zhangwenhao66/awesome-customer-support-software" target="_blank" rel="noopener noreferrer">awesome-customer-support-software ${icon('ExternalLink')}</a><small>资源清单 · 历史排序误选</small></div></div>`:''}<div class="metric-row"><div class="metric"><strong>${stage<2?3:stage===2?10:stage===3?11:0}</strong><span>${stage<2?'仓库查询':stage===2?'仓库内查询':stage===3?'补充查询':'可用来源候选'}</span></div><div class="metric"><strong>0</strong><span>匹配的 Issue</span></div></div><button class="text-button" data-action="attempts">查看原始检索记录 ${icon('ArrowRight')}</button><p class="note-block">此案例来自旧版运行。仓库质量问题属于后续复盘结论，不代表当时 Agent 已自动识别并修复。</p>`;
  }
  if (stage===0) return `<div class="surface-head"><h2>研究从哪里开始</h2>${tag('已确认')}</div><p class="small muted">从学生笔记工具出发，探索整理、搜索、复习与跨设备工作流中的产品机会。</p><dl class="boundary-list"><div><dt>历史输入</dt><dd>类似 GoodNotes 的笔记应用，面向学生</dd></div><div><dt>实际证据</dt><dd>以 Logseq 的通用笔记工作流为主</dd></div></dl><p class="note-block">学生身份和手写体验在公开证据中的覆盖有限，不能把后续结果直接认定为学生专属需求。</p>`;
  if (stage===1) return `<div class="surface-head"><h2>来源与研究范围</h2>${tag('人工确认','blue')}</div>${data.note.approvedRepos.map((repo,index)=>`<div class="source-row"><span class="source-monogram">${index?'J':'L'}</span><div class="source-copy"><a href="https://github.com/${repo}" target="_blank" rel="noopener noreferrer">${repo} ${icon('ExternalLink')}</a><small>${index?'已确认来源 · 本次最终采集样本未覆盖':'已确认来源 · 最终 50 条采集样本来自此仓库'}</small></div></div>`).join('')}<p class="note-block">开源笔记工具主要提供整理、搜索和跨设备使用的证据。GoodNotes 手写体验与学生专属场景的覆盖仍有限。</p><button class="text-button" data-action="source-review" style="margin-top:15px">查看确认记录 ${icon('FileText')}</button>`;
  if (stage===2) return `<div class="surface-head"><h2>采集与分析口径</h2>${tag('已采集')}</div><div class="metric-row"><div class="metric"><strong>50</strong><span>有效 Issue</span></div><div class="metric"><strong>150</strong><span>保存的评论内容</span></div><div class="metric"><strong>37</strong><span>程序评为高信号</span></div></div><dl class="detail-list"><div><dt>采集范围</dt><dd>Logseq · 跳过 2 条 PR</dd></div><div><dt>评论内容</dt><dd>每个 Issue 最多保存 3 条</dd></div><div><dt>评论元数据总数</dt><dd>1,084，非全部已阅读或保存</dd></div><div><dt>反应元数据总数</dt><dd>425</dd></div></dl><p class="note-block">“高信号”是程序评分，不等于经过访谈验证的高价值需求。数字来自历史采集快照。</p>`;
  if (stage===3) return `<div class="surface-head"><h2>从问题到机会方向</h2>${tag('痛点归纳')}</div>${translations.map(item=>`<div class="theme-row">${icon(item.icon)}${item.title}</div>`).join('')}<p class="note-block">以上是机会卡归纳出的研究方向。历史报告另记录了 embedding 聚类：49 个痛点归为 48 个簇，合并 1 组相似痛点；不等于聚类直接得到了这 3 个方向。</p>`;
  return `<div class="surface-head"><h2>有证据，也保留不确定性</h2>${tag('研究完成')}</div><div class="metric-row"><div class="metric"><strong>3</strong><span>机会假设</span></div><div class="metric"><strong>2</strong><span>建议进一步验证</span></div><div class="metric"><strong>1</strong><span>建议继续观察</span></div></div><p class="small muted">每张机会卡包含痛点、当前替代方案、MVP 方向和具体 Issue 链接。商业化方案仍属于假设。</p><p class="note-block">研究结果主要面向跨设备笔记用户、大型图谱用户和 Android 用户；实际人群以证据为准。</p>`;
}
function renderResults() {
  if (state.scenario==='partial') return renderPartial();
  return `<div class="page-heading result-heading"><div><div class="eyebrow">03 / 研究结果</div><h1>3 个值得继续验证的方向</h1><div class="result-metrics"><span><b>50</b> 有效 Issue</span><span><b>3</b> 机会卡</span><span><b>2</b> 人工确认来源</span></div></div><a class="button" href="assets/report.zh.md" download="note-research-report.md">${icon('Download')}导出历史报告</a></div>
    <div class="scope-notice">${icon('Info')}<span>实际采集的 50 条 Issue 来自 Logseq。以下人群按证据描述，尚不能直接认定为学生专属需求。</span></div>
    <div class="cards">${translations.map((item,index)=>`<article class="opportunity-card"><div class="card-icon">${icon(item.icon)}</div><div><h2 class="card-title">${item.title}</h2><p class="card-audience">${item.user}</p><p class="card-pain">${item.pain}</p><div class="card-footer"><button class="text-button" data-card="${index}" data-tab="evidence">${icon('MessageSquare')}${data.note.cards[index].evidence_urls.length} 条 Issue 证据</button><button class="text-button" data-card="${index}" data-tab="validation">查看验证计划 ${icon('ArrowRight')}</button></div></div><div class="card-meta">${tag(index===2?'继续观察':'建议验证',index===2?'amber':'green')}<p>历史置信度：${index===2?'较低':'中等'}</p><button class="button" data-card="${index}" data-tab="overview">查看机会详情${icon('ChevronRight')}</button></div></article>`).join('')}</div>
    <div class="evidence-boundary"><strong>证据支持痛点，商业价值仍待验证。</strong>Issue 数量不能推算需求规模；方案可行性、用户覆盖与付费意愿需要进一步验证。链接对应历史证据，Issue 当前状态可能已经变化。</div>
    <div class="actions">${button('查看研究过程','process','ArrowLeft')}<button class="text-button" data-action="switch-partial">查看“证据不足”案例 ${icon('ArrowRight')}</button></div>`;
}
function renderPartial() {
  return `<div class="page-heading"><div class="eyebrow">03 / 研究结果</div><h1>证据不足，暂不生成机会卡</h1><p>客服 Agent 研究 · 独立历史案例</p></div><div class="flow-summary warn"><div><strong>没有形成可用的来源候选</strong><p>本轮查询返回 0 条匹配 Issue，无法支持机会生成。</p></div>${tag('Partial','amber')}</div>
    <section class="empty-surface"><div class="empty-icon">${icon('Search')}</div><h2>这次缺少的是可用证据</h2><p>历史检索将预算分配给了一个预约系统和一个资源清单，未找到足够相关的公开 Issue。这不能说明在线客服领域没有需求。</p><div class="metric-row"><div class="metric"><strong>${data.partial.attempts.length}</strong><span>历史检索请求</span></div><div class="metric"><strong>0</strong><span>可用来源候选</span></div><div class="metric"><strong>0</strong><span>生成的机会卡</span></div></div><h3>建议下一步 <span class="tag blue">复盘建议</span></h3><ol class="next-steps"><li>复核候选仓库：是否为实际客服产品，而非资源清单或相邻领域项目。</li><li>将检索预算优先分配给相关产品，检查 Issue 查询是否适合用户实际用语。</li><li>重新采集后再判断证据是否足够，保留研究方向与已有草稿。</li></ol><div class="link-group">${button('查看检索记录','attempts','FileText',true)}${button('返回研究边界','input','ArrowLeft')}</div><p class="note-block">以上是基于该旧版案例的复盘建议。当前原型不会执行重跑，也不表示修复后已验证成功。</p></section><div class="actions">${button('查看研究过程','process','ArrowLeft')}<button class="text-button" data-action="switch-note">返回笔记工具案例 ${icon('ArrowRight')}</button></div>`;
}
function startPlayback() {
  clearInterval(playback);
  state.playing=true;
  if (!state.completed) state.completed=1;
  render();
  playback=setInterval(()=>{
    state.completed=Math.min(5,state.completed+1);
    state.selectedStage=state.completed-1;
    if(state.completed===5){state.playing=false;clearInterval(playback);}
    render();
  },1400);
}
function stopPlayback(){clearInterval(playback);state.playing=false;}
function goPage(page) {
  if (page>0&&!state.approved || page===2&&state.completed<5) return;
  if(page!==1) stopPlayback();
  state.page=page;render();window.scrollTo({top:0,behavior:'instant'});
}
function switchScenario(scenario) {
  stopPlayback();
  Object.assign(state,{scenario,page:0,approved:false,completed:0,selectedStage:0,playing:false,keywords:[],query:examples[scenario],showKeywords:false});
  render();window.scrollTo({top:0,behavior:'instant'});
  notify(`已切换到${names[scenario]}，这是另一条独立历史记录。`);
}
function openDialog(title,subtitle,body,tabs='') {
  if(!dialog.open) dialogFocus=document.activeElement;
  dialog.innerHTML=`<div class="dialog-head"><div><h2 id="dialog-title">${title}</h2><p>${subtitle}</p></div>${iconButton('X','close-dialog','关闭详情')}</div>${tabs}<div class="dialog-body">${body}</div>`;
  if(!dialog.open) dialog.showModal();
}
function closeDialog(){dialog.close();if(dialogFocus?.isConnected)dialogFocus.focus();}
function showCard(index,tab='overview') {
  selectedCard=index;
  const item=translations[index];
  const original=data.note.cards[index];
  const tabs=`<div class="dialog-tabs" role="tablist" aria-label="机会详情">${[['overview','机会判断'],['evidence','原始证据'],['validation','验证计划']].map(([id,label])=>`<button role="tab" id="tab-${id}" aria-controls="card-panel" aria-selected="${id===tab}" tabindex="${id===tab?0:-1}" class="${id===tab?'active':''}" data-dialog-tab="${id}">${label}</button>`).join('')}</div>`;
  let body;
  if(tab==='overview') body=`<h3>目标用户</h3><p>${item.user}</p><h3>观察到的痛点</h3><p>${item.pain}</p><h3>用户现在怎么处理</h3><p>${item.workaround}</p><h3>MVP 方向</h3><p>${item.mvp}</p><h3>商业化假设</h3><p>${item.commercial}</p><div class="callout">${item.assumption}</div>`;
  else if(tab==='evidence') body=`<p>以下 ${original.evidence_urls.length} 条 Issue 均能在本 run 的原始采集文件中找到。标题保留英文原文，计数和状态来自历史快照。</p>${original.evidence_urls.map(url=>{const evidence=data.note.evidence.find(row=>row.url===url);return `<article class="evidence-item"><a href="${url}" target="_blank" rel="noopener noreferrer">#${evidence.id} · ${escapeHtml(evidence.title)} ${icon('ExternalLink')}</a><div class="evidence-meta">logseq/logseq · 历史状态 ${evidence.state} · ${evidence.comments_count} 条评论元数据 · ${evidence.reactions_count} 次反应</div></article>`;}).join('')}<div class="callout">来源链接不等于结论已获验证。点击原文可进一步检查问题上下文、后续修复及方案是否仍有价值。</div>`;
  else body=`<h3>建议下一步</h3><p>${item.next}</p><ol>${item.validation.map(text=>`<li>${text}</li>`).join('')}</ol><h3>需要验证的风险</h3><p>${item.risk}</p><div class="callout">这是待执行的验证计划；当前没有访谈结果、原型测试结果或付费意愿结论。</div>`;
  openDialog(item.title,`${index===2?'继续观察':'建议验证'} · 历史置信度${index===2?'较低':'中等'}`,`<section id="card-panel" role="tabpanel" aria-labelledby="tab-${tab}">${body}</section>`,tabs);
}
function showAttempts(){
  const stageLabels={repository:'仓库检索',repo_scoped_issue:'仓库内 Issue',global_issue_safety_net:'全局补充',expansion:'扩展查询'};
  openDialog('客服案例 · 检索记录',`${data.partial.runId} · ${data.partial.attempts.length} 次历史请求`,`<p>检索成功指请求执行成功，不表示找到了有效证据。下表保留历史查询内容，包括当时重复执行的查询。</p><div class="table-wrap"><table><thead><tr><th>阶段</th><th>原始查询</th><th>返回数量</th></tr></thead><tbody>${data.partial.attempts.map(row=>`<tr><td>${stageLabels[row.stage]||escapeHtml(row.stage)}</td><td class="query">${escapeHtml(row.query)}</td><td>${row.result_count}</td></tr>`).join('')}</tbody></table></div><h3>当时记录的诊断建议</h3><ul>${data.partial.originalActions.map(text=>`<li>${escapeHtml(text)}</li>`).join('')}</ul><p>页面中的仓库质量复盘是后续分析，不是这份旧诊断原文。</p>`);
}
function caseDetails(){
  const note=state.scenario==='note';
  openDialog('案例记录与数据口径',note?data.note.runId:data.partial.runId,`<dl class="detail-list"><div><dt>展示模式</dt><dd>本地交互原型，历史结果回放</dd></div><div><dt>当前案例</dt><dd>${names[state.scenario]}</dd></div><div><dt>输入与关键词</dt><dd>中文示例和页面编辑属于原型草稿，不会调用 Agent 或生成新结果</dd></div>${note?`<div><dt>历史采集日期</dt><dd>${data.note.collectedAt}</dd></div><div><dt>报告状态</dt><dd>success</dd></div><div><dt>来源确认</dt><dd>人工确认 Logseq、Joplin；最终 50 条采集记录全部来自 Logseq</dd></div><div><dt>评论口径</dt><dd>1,084 条为元数据计数，实际保存 150 条评论内容</dd></div><div><dt>程序评分</dt><dd>37 条 Issue 被历史程序评为高信号，非用户验证结论</dd></div><div><dt>聚类记录</dt><dd>报告记载 49 个痛点归为 48 个簇；3 张机会卡不等于 3 个聚类</dd></div>`:`<div><dt>来源候选</dt><dd>0，历史查询未形成可用证据</dd></div><div><dt>复盘边界</dt><dd>页面中的仓库质量分析为后续复盘，不表示历史运行自动识别了问题</dd></div>`}</dl>${note?`<h3>历史文件</h3><div class="link-group"><a class="button" href="assets/report.zh.md" download>中文报告 ${icon('Download')}</a><a class="button" href="assets/opportunity-cards.json" download>原始机会卡 ${icon('Download')}</a></div>`:''}<div class="callout">时间线展示顺序和播放速度属于原型演示，并非原始运行耗时。此案例不能作为当前版本召回率或商业价值已验证的证明。</div>`);
}
document.addEventListener('click',event=>{
  const target=event.target.closest('button,a');
  if(!target)return;
  if(target.dataset.page!==undefined){goPage(Number(target.dataset.page));return;}
  if(target.dataset.stage!==undefined){state.selectedStage=Number(target.dataset.stage);stopPlayback();render();return;}
  if(target.dataset.card!==undefined){showCard(Number(target.dataset.card),target.dataset.tab);return;}
  if(target.dataset.dialogTab){showCard(selectedCard,target.dataset.dialogTab);dialog.querySelector(`[data-dialog-tab="${target.dataset.dialogTab}"]`).focus();return;}
  if(target.dataset.removeKeyword!==undefined){state.keywords.splice(Number(target.dataset.removeKeyword),1);render();return;}
  const action=target.dataset.action;
  if(!action)return;
  event.preventDefault();
  switch(action){
    case 'home':case 'input':goPage(0);break;
    case 'process':goPage(1);break;
    case 'results':goPage(2);break;
    case 'toggle-keywords':state.showKeywords=!state.showKeywords;render();if(state.showKeywords)document.getElementById('keyword-input').focus();break;
    case 'approve':if(!state.query.trim())return;state.approved=true;state.page=1;state.completed=1;state.selectedStage=0;startPlayback();window.scrollTo(0,0);if(isDraft())notify('草稿已保留；正在回放历史结果，未执行新检索。');break;
    case 'toggle-play':if(state.playing){stopPlayback();render();}else startPlayback();break;
    case 'skip':stopPlayback();state.completed=5;state.selectedStage=4;render();break;
    case 'replay':state.completed=1;state.selectedStage=0;startPlayback();break;
    case 'switch-partial':switchScenario('partial');break;
    case 'switch-note':switchScenario('note');break;
    case 'close-dialog':closeDialog();break;
    case 'attempts':showAttempts();break;
    case 'case-details':caseDetails();break;
    case 'source-review':openDialog('来源人工确认记录','历史文件中保留了一处状态文案不一致',`<p>最终状态为 approved，confirmed_by 为 human。Logseq 与 Joplin 被放在 approved_sources 中，但 reason 仍写着旧的 Auto-rejected 文案。</p><div class="callout">页面将它表述为“人工确认来源”，不会把这次历史记录包装为自动批准成功。</div><h3>原始记录</h3><pre class="mono" style="white-space:pre-wrap;font-size:12px">${escapeHtml(JSON.stringify(data.note.sourceReview,null,2))}</pre>`);break;
    case 'about':openDialog('关于这个研究原型','交互设计与真实产物，各自保留边界',`<h3>你正在查看什么</h3><p>三屏研究流程：确认方向、查看过程、检查机会卡。右上角可切换笔记工具成功案例与客服证据不足案例。</p><h3>哪些来自历史运行</h3><p>笔记案例的 Issue 数量、机会卡、来源链接和报告来自同一次已保存的 run；客服案例的查询和零候选结果来自另一条历史 run。</p><h3>哪些是演示交互</h3><p>中文简短输入、关键词编辑、确认按钮及时间线播放均为原型交互。没有后端请求，输入变化不会改变历史结果。</p>`);break;
  }
});
document.addEventListener('input',event=>{
  if(event.target.id==='research-query'){
    state.query=event.target.value;
    document.getElementById('approve-button').disabled=!state.query.trim();
    document.getElementById('draft-note').hidden=!isDraft();
  }
});
document.addEventListener('submit',event=>{
  if(event.target.id!=='keyword-form')return;
  event.preventDefault();
  const input=document.getElementById('keyword-input');
  const word=input.value.trim();
  if(!word)return;
  if(state.keywords.length>=8){notify('最多保留 8 个重要关键词。');return;}
  if(state.keywords.some(item=>item.toLocaleLowerCase()===word.toLocaleLowerCase())){notify('这个关键词已经添加。');return;}
  state.keywords.push(word);render();document.getElementById('keyword-input').focus();
});
document.addEventListener('change',event=>{if(event.target.id==='case-picker')switchScenario(event.target.value);});
dialog.addEventListener('click',event=>{if(event.target===dialog){const bounds=dialog.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)closeDialog();}});
dialog.addEventListener('cancel',()=>{if(dialogFocus?.isConnected)dialogFocus.focus();});
dialog.addEventListener('keydown',event=>{
  if(event.target.getAttribute('role')!=='tab'||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();
  const tabs=['overview','evidence','validation'];
  const current=tabs.indexOf(event.target.dataset.dialogTab);
  const next=event.key==='Home'?0:event.key==='End'?2:(current+(event.key==='ArrowRight'?1:2))%3;
  showCard(selectedCard,tabs[next]);dialog.querySelector(`[data-dialog-tab="${tabs[next]}"]`).focus();
});
render();
