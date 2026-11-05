// Same check as isHttpsUrl in the website repo (osimyoter-website src/shortLinks/shortLinks.ts),
// run on the same WHATWG URL parser the browser uses. Keep the two in step.
// Reads a JSON array of values on stdin, prints a JSON array of booleans.
function isHttpsUrl(value) {
  if (typeof value !== 'string' || !value.startsWith('https://')) return false
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}

let input = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', (chunk) => { input += chunk })
process.stdin.on('end', () => { process.stdout.write(JSON.stringify(JSON.parse(input).map(isHttpsUrl))) })
