export const avatar = {
  id: "openrouter:heygen/avatar-iv", label: "Avatar IV test fixture", kind: "video", provider: "openrouter",
  roles: { image: 1 }, required_roles: { image: 1 }, credential_configured: true,
  prompt_label: "Текст речи", rate_per_second: 0.05,
  input_note: "Одно фото + текст речи. Укажите Voice ID HeyGen в параметрах. Аудиофайлы пока не подключены.",
  pricing_note: "$0.05 за секунду результата; длительность определяется речью. Итог после генерации.",
  settings: {
    resolution: {type:"enum", values:["720p","1080p"], default:"720p"},
    aspect_ratio: {type:"enum", values:["16:9","9:16","1:1"], default:"16:9"},
    voice_id: {type:"string", required:true, title:"Голос HeyGen · Voice ID", description:"Voice ID из каталога голосов HeyGen"},
    motion_prompt: {type:"string", title:"Движения персонажа"},
    expressiveness: {type:"enum", values:["low","medium","high"], default:"low"},
    fit: {type:"enum", values:["contain","cover"], default:"contain"},
    remove_background: {type:"boolean", default:false},
  },
};
