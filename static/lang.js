// 语言对：我的语言 L.me / 对方的语言 L.them（默认 中文⇄西语），存在 localStorage。
const LANGS = {  // code: [中文名, 短标, 本语言名]
  zh: ['中文', '中', '中文'], es: ['西班牙语', '西', 'Español'], en: ['英语', '英', 'English'], fr: ['法语', '法', 'Français'],
  de: ['德语', '德', 'Deutsch'], it: ['意大利语', '意', 'Italiano'], pt: ['葡萄牙语', '葡', 'Português'], ar: ['阿拉伯语', '阿', 'العربية'],
  ru: ['俄语', '俄', 'Русский'], ja: ['日语', '日', '日本語'], ko: ['韩语', '韩', '한국어'], nl: ['荷兰语', '荷', 'Nederlands'],
  pl: ['波兰语', '波', 'Polski'], tr: ['土耳其语', '土', 'Türkçe'], uk: ['乌克兰语', '乌', 'Українська'], vi: ['越南语', '越', 'Tiếng Việt'],
  hi: ['印地语', '印', 'हिन्दी'] };
const L = { me: LANGS[localStorage.langMe] ? localStorage.langMe : 'zh', them: LANGS[localStorage.langThem] ? localStorage.langThem : 'es' };
if (L.me === L.them) { L.me = 'zh'; L.them = 'es'; }
const isMine = (lang) => (lang || L.them).split('-')[0] === L.me;
// 对坐上半屏给对方看的小按钮文字（对方语言，没有就英语）
const UI_THEM = { latest: { es: 'Último ↓', en: 'Latest ↓', fr: 'Dernier ↓', de: 'Neueste ↓', it: 'Ultimo ↓', pt: 'Último ↓', ru: 'Новое ↓',
  ja: '最新 ↓', ko: '최신 ↓', ar: 'الأحدث ↓', nl: 'Nieuwste ↓', pl: 'Najnowsze ↓', tr: 'En yeni ↓', uk: 'Нове ↓', vi: 'Mới nhất ↓', hi: 'नवीनतम ↓', zh: '最新 ↓' } };
const tThem = (k) => UI_THEM[k][L.them] || UI_THEM[k].en;
// 试听句子（对方语言）
const SAMPLE = { es: 'Hola, encantada. ¿Me puede traer la cuenta, por favor?', en: 'Hello, nice to meet you. Could you bring the bill, please?',
  fr: "Bonjour, enchantée. Pourriez-vous m'apporter l'addition, s'il vous plaît ?", de: 'Hallo, freut mich. Könnten Sie mir bitte die Rechnung bringen?',
  it: 'Ciao, piacere. Mi può portare il conto, per favore?', pt: 'Olá, muito prazer. Pode trazer a conta, por favor?', zh: '你好，很高兴认识你。请帮我结一下账。',
  ru: 'Здравствуйте, очень приятно. Принесите, пожалуйста, счёт.', ja: 'こんにちは。お会計をお願いします。', ko: '안녕하세요. 계산서 좀 주시겠어요?',
  ar: 'مرحبا، تشرفنا. هل يمكنك إحضار الفاتورة من فضلك؟' };
