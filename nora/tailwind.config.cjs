const original = require("../packages/studio/tailwind.config.js");
module.exports = {
  ...original,
  content: ["../packages/studio/src/**/*.{js,jsx}", "./src/**/*.{js,jsx}"],
};
