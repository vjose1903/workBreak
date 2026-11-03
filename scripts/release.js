#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline/promises');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');

function git(cwd, ...args) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

function parseVersion(value) {
  const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(value);
  if (!match) throw new Error(`Versión inválida: "${value}". Usa X.Y.Z.`);
  const numbers = match.slice(1).map(Number);
  if (numbers.some((number, index) => !Number.isSafeInteger(number) || number > [9999, 99, 99][index])) {
    throw new Error('La versión supera el límite de macOS: 9999.99.99.');
  }
  return numbers;
}

function calculateVersion(current, kind) {
  let [major, minor, patch] = parseVersion(current);
  if (kind === 'mayor' || kind === 'major') [major, minor, patch] = [major + 1, 0, 0];
  else if (kind === 'version' || kind === 'minor') [major, minor, patch] = [major, minor + 1, 0];
  else if (kind === 'parche' || kind === 'patch') patch += 1;
  else if (kind !== 'actual') throw new Error('Elige mayor, version, parche o actual.');
  const target = `${major}.${minor}.${patch}`;
  parseVersion(target);
  return target;
}

function compareVersions(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return 0;
}

function checkTag(cwd, tag) {
  const current = fs.readFileSync(path.join(cwd, 'VERSION'), 'utf8').trim();
  parseVersion(current);
  if (tag !== `v${current}`) throw new Error(`El tag "${tag}" no coincide con VERSION (${current}).`);
  return current;
}

function planRelease(cwd, kind) {
  if (fs.realpathSync(git(cwd, 'rev-parse', '--show-toplevel')) !== fs.realpathSync(cwd)) {
    throw new Error('No estás en la raíz del checkout de WorkBreak.');
  }
  const branch = git(cwd, 'branch', '--show-current');
  if (!branch) throw new Error('No se puede publicar desde HEAD separado. Cambia primero a una rama.');
  if (git(cwd, 'diff', '--name-only', '--diff-filter=U')) throw new Error('Resuelve los conflictos antes de publicar.');
  git(cwd, 'var', 'GIT_AUTHOR_IDENT');
  const current = fs.readFileSync(path.join(cwd, 'VERSION'), 'utf8').trim();
  const target = calculateVersion(current, kind);
  const tag = `v${target}`;
  const localTag = git(cwd, 'tag', '--list', tag);
  const status = git(cwd, 'status', '--short');
  const head = git(cwd, 'rev-parse', 'HEAD');
  const resume = kind === 'actual' && !!localTag && !status
    && git(cwd, 'rev-parse', `${tag}^{commit}`) === head;
  if (localTag && !resume) throw new Error(`El tag local ${tag} ya existe. No se reemplazan tags publicados.`);
  const refs = git(cwd, 'ls-remote', 'origin', `refs/heads/${branch}`, 'refs/tags/v*');
  let remoteHead;
  for (const line of refs.split('\n').filter(Boolean)) {
    const [sha, ref] = line.split(/\s+/);
    if (ref === `refs/tags/${tag}` && !resume) throw new Error(`El tag ${tag} ya existe en origin.`);
    const remoteVersion = /^refs\/tags\/v((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$/.exec(ref);
    if (remoteVersion && compareVersions(target, remoteVersion[1]) < 0) {
      throw new Error(`La versión ${target} es anterior al tag remoto v${remoteVersion[1]}. Actualiza VERSION.`);
    }
    if (ref === `refs/heads/${branch}`) remoteHead = sha;
  }
  if (resume) {
    const remoteTag = git(cwd, 'ls-remote', 'origin', `refs/tags/${tag}`, `refs/tags/${tag}^{}`);
    const commits = remoteTag.split('\n').filter(Boolean);
    const resolved = commits.find(line => line.endsWith('^{}')) || commits[0];
    if (resolved && resolved.split(/\s+/)[0] !== head) throw new Error('El tag remoto apunta a otro commit; no se modificará.');
  }
  if (remoteHead) {
    try {
      git(cwd, 'merge-base', '--is-ancestor', remoteHead, 'HEAD');
    } catch {
      throw new Error(`Sincroniza la rama ${branch} con origin antes de publicar. No se hará push forzado.`);
    }
  }
  return { resume, current, target, tag, branch, head: git(cwd, 'rev-parse', 'HEAD'),
    status: git(cwd, 'status', '--short') };
}

function publishRelease(cwd, plan, description, { dryRun = false } = {}) {
  if (!description.trim()) throw new Error('La descripción no puede estar vacía.');
  if (dryRun) return;
  if (git(cwd, 'branch', '--show-current') !== plan.branch || git(cwd, 'rev-parse', 'HEAD') !== plan.head || git(cwd, 'status', '--short') !== plan.status
      || fs.readFileSync(path.join(cwd, 'VERSION'), 'utf8').trim() !== plan.current) {
    throw new Error('El checkout cambió mientras preparabas la publicación. Vuelve a ejecutar el comando.');
  }
  if (plan.resume) {
    git(cwd, 'push', '--atomic', 'origin', `HEAD:refs/heads/${plan.branch}`, `refs/tags/${plan.tag}`);
    return;
  }
  const summary = `release: WorkBreak ${plan.tag}`;
  let committed = false;
  let tagged = false;
  try {
    fs.writeFileSync(path.join(cwd, 'VERSION'), `${plan.target}\n`);
    git(cwd, 'add', '-A');
    if (git(cwd, 'diff', '--cached', '--name-only')) {
      git(cwd, 'commit', '-m', summary, '-m', description.trim());
      committed = true;
    }
    if (git(cwd, 'show', 'HEAD:VERSION') !== plan.target) {
      throw new Error('El commit no contiene la VERSION esperada. Revisa los hooks de Git antes de publicar.');
    }
    git(cwd, 'tag', '-a', plan.tag, '-m', summary, '-m', description.trim());
    tagged = true;
    // GitHub recibe la rama y el tag juntos, o rechaza ambos.
    git(cwd, 'push', '--atomic', 'origin', `HEAD:refs/heads/${plan.branch}`, `refs/tags/${plan.tag}`);
  } catch (error) {
    const detail = error.stderr ? String(error.stderr).trim() : error.message;
    const recovery = tagged
      ? `El commit y ${plan.tag} siguen locales. Reintenta: git push --atomic origin HEAD:refs/heads/${plan.branch} refs/tags/${plan.tag}`
      : committed ? `El commit sigue local. Falta crear y publicar ${plan.tag}.`
        : 'Los cambios siguen en el checkout. Revisa VERSION y el área de staging antes de reintentar.';
    throw new Error(`${detail}\n${recovery}\nNo se han borrado cambios ni se ha hecho push forzado.`);
  }
}

function parseArgs(args) {
  const options = { dryRun: false };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === '--dry-run') options.dryRun = true;
    else if (arg === '--help' || arg === '-h') options.help = true;
    else if (['--kind', '--description', '--check-tag'].includes(arg)) {
      if (!args[index + 1] || args[index + 1].startsWith('--')) throw new Error(`Falta el valor de ${arg}.`);
      options[{ '--kind': 'kind', '--description': 'description', '--check-tag': 'tag' }[arg]] = args[++index];
    } else throw new Error(`Opción desconocida: ${arg}`);
  }
  return options;
}

function gh(cwd, args, { interactive = false } = {}) {
  return execFileSync('gh', args, { cwd, encoding: 'utf8',
    stdio: interactive ? 'inherit' : ['ignore', 'pipe', 'pipe'],
    ...(interactive ? {} : { timeout: 30_000 }) });
}

function prepareGitHub(cwd, run = gh) {
  try {
    run(cwd, ['auth', 'status']);
    const { nameWithOwner } = JSON.parse(run(cwd, ['repo', 'view', '--json', 'nameWithOwner']));
    if (!/^[\w.-]+\/[\w.-]+$/.test(nameWithOwner)) throw new Error('Repositorio GitHub inválido.');
    run(cwd, ['api', `repos/${nameWithOwner}/actions/runs?per_page=1`]);
    return nameWithOwner;
  } catch (error) {
    const detail = error.stderr ? String(error.stderr).trim() : error.message;
    throw new Error(`No se puede preparar GitHub Actions. Necesitas GitHub CLI (gh) instalado y autenticado con acceso al repositorio y Actions.\n${detail}\nNo se han creado commits ni tags.`);
  }
}

async function completeRelease(cwd, plan, repo, {
  run = gh, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), attempts = 20,
} = {}) {
  const sha = git(cwd, 'rev-parse', `${plan.tag}^{commit}`);
  const workflow = 'release-macos.yml';
  async function findRun() {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const runs = JSON.parse(run(cwd, ['run', 'list', '--repo', repo, '--workflow', workflow,
        '--commit', sha, '--limit', '20', '--json', 'databaseId,event,headBranch,url,conclusion']));
      const found = runs.find(item => item.headBranch === plan.tag
        && ['push', 'workflow_dispatch'].includes(item.event));
      if (found) return found;
      if (attempt + 1 < attempts) await sleep(3000);
    }
    return null;
  }
  console.log(`\nEsperando la compilación de ${plan.tag} para Intel y Apple Silicon…`);
  let build = await findRun();
  if (!build) {
    console.log('El push no inició el workflow. Iniciándolo automáticamente para este tag…');
    run(cwd, ['workflow', 'run', workflow, '--repo', repo, '--ref', plan.tag, '-f', `tag=${plan.tag}`]);
    build = await findRun();
  }
  if (!build) throw new Error(`GitHub no registró la compilación de ${plan.tag}. El tag ya está publicado; no se ha reemplazado.`);
  if (plan.resume && ['failure', 'cancelled', 'timed_out', 'action_required'].includes(build.conclusion)) {
    run(cwd, ['run', 'rerun', String(build.databaseId), '--repo', repo]);
  }
  console.log(`Compilación: ${build.url}`);
  try {
    run(cwd, ['run', 'watch', String(build.databaseId), '--repo', repo, '--exit-status', '--interval', '10'],
      { interactive: true });
  } catch {
    throw new Error(`La compilación/publicación de ${plan.tag} falló. No se confirma una descarga disponible. Revisa ${build.url}`);
  }
  const release = JSON.parse(run(cwd, ['api', `repos/${repo}/releases/tags/${plan.tag}`]));
  const names = ['arm64', 'x86_64'].flatMap(arch => [
    `WorkBreak-${plan.target}-macos-${arch}.dmg`, `WorkBreak-macos-${arch}.dmg`,
  ]);
  if (release.draft || release.prerelease || release.tag_name !== plan.tag
      || !names.every(name => (release.assets || []).some(asset => asset.name === name && asset.state === 'uploaded'))) {
    throw new Error(`La Release ${plan.tag} no está publicada con todos los DMG versionados y dinámicos. Revisa ${build.url}`);
  }
  console.log(`\n${plan.tag} lista para descargar: ${release.html_url}`);
  for (const arch of ['arm64', 'x86_64']) {
    console.log(`https://github.com/${repo}/releases/latest/download/WorkBreak-macos-${arch}.dmg`);
  }
  return release;
}

async function main(args = process.argv.slice(2)) {
  const options = parseArgs(args);
  if (options.help) {
    console.log('Uso: node scripts/release.js [--dry-run] [--kind parche|version|mayor|actual] [--description "Cambios"]');
    return;
  }
  if (options.tag) {
    checkTag(root, options.tag);
    console.log(`Tag ${options.tag} y VERSION comprobados.`);
    return;
  }
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  try {
    const current = fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim();
    console.log(`\nWorkBreak · versión actual ${current}`);
    let kind = options.kind;
    if (!kind) {
      console.log('  1. Mayor: cambio incompatible\n  2. Versión: nueva funcionalidad\n  3. Parche: corrección\n  4. Actual: publicar o reanudar VERSION sin incrementarla');
      kind = { 1: 'mayor', 2: 'version', 3: 'parche', 4: 'actual' }[(await rl.question('Elige 1, 2, 3 o 4: ')).trim()];
      if (!kind) throw new Error('Debes elegir 1, 2, 3 o 4.');
    }
    const plan = planRelease(root, kind);
    const description = options.description ?? (await rl.question('¿Qué incluye esta actualización? ')).trim();
    if (!description.trim()) throw new Error('La descripción no puede estar vacía.');
    console.log(`\nRama: ${plan.branch}\nVersión: ${plan.current} → ${plan.target}\nTag: ${plan.tag}\nDescripción: ${description}`);
    console.log('\nSe incluirán todos los cambios del proyecto que no estén ignorados por Git:');
    console.log(plan.status || '(checkout limpio)');
    if (options.dryRun) {
      console.log('\nSimulación terminada. No se modificó VERSION, no se crearon commits ni tags y no se publicó nada.');
      return;
    }
    const repo = prepareGitHub(root);
    if ((await rl.question('\n¿Publicar esta versión y sus cambios? [s/N]: ')).trim().toLowerCase() !== 's') {
      console.log('Publicación cancelada.');
      return;
    }
    publishRelease(root, plan, description);
    await completeRelease(root, plan, repo);
  } finally {
    rl.close();
  }
}

if (require.main === module) {
  main().catch(error => {
    console.error('No se pudo publicar:', JSON.stringify({ error: error.message }));
    process.exitCode = 1;
  });
}

module.exports = { calculateVersion, checkTag, parseArgs, planRelease, publishRelease, prepareGitHub, completeRelease };
