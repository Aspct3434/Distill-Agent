#!/usr/bin/env node

const { main } = require("../lib/distill-cli");

main(process.argv.slice(2)).catch((error) => {
  const message = error && error.message ? error.message : String(error);
  console.error(`\nDistill installer failed: ${message}`);
  process.exitCode = 1;
});
