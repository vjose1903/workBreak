'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { calculateVersion, checkTag, parseArgs, planRelease, publishRelease, prepareGitHub, completeRelease } = require('../scripts/release.js');

function git(cwd, ...args) {
  return execFileSync('git', args, { cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

function repository(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'workbreak-release-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const root = path.join(dir, 'checkout');
  const origin = path.join(dir, 'origin.git');
  fs.mkdirSync(root);
  git(dir, 'init', '--bare', origin);
  git(root, 'init', '-b', 'main');
  git(root, 'config', 'user.name', 'Pruebas WorkBreak');
  git(root, 'config', 'user.email', 'tests@example.invalid');
  fs.writeFileSync(path.join(root, 'VERSION'), '1.0.0\n');
  fs.writeFileSync(path.join(root, 'app.py'), 'contenido inicial\n');
  git(root, 'add', '.');
  git(root, 'commit', '-m', 'Inicial');
  git(root, 'remote', 'add', 'origin', origin);
  git(root, 'push', '-u', 'origin', 'main');
  return { root, origin };
}

test('calcula versiones y rechaza formatos o límites inválidos', () => {
  assert.equal(calculateVersion('1.9.9', 'parche'), '1.9.10');
  assert.equal(calculateVersion('1.9.9', 'version'), '1.10.0');
  assert.equal(calculateVersion('1.9.9', 'mayor'), '2.0.0');
  assert.equal(calculateVersion('1.9.9', 'actual'), '1.9.9');
  for (const version of ['01.0.0', '1.0', '../1.0.0', '1.0.0-beta']) {
    assert.throws(() => calculateVersion(version, 'parche'));
  }
  assert.throws(() => calculateVersion('1.0.99', 'parche'));
  assert.throws(() => calculateVersion('1.0.0', 'desconocido'));
});

test('comprueba que el tag coincida exactamente con VERSION', t => {
  const { root } = repository(t);
  assert.equal(checkTag(root, 'v1.0.0'), '1.0.0');
  assert.throws(() => checkTag(root, 'v1.0.1'));
  assert.throws(() => checkTag(root, '1.0.0'));
});

test('dry-run no cambia archivos, staging, commits ni tags', t => {
  const { root, origin } = repository(t);
  fs.appendFileSync(path.join(root, 'app.py'), 'nueva funcionalidad\n');
  const plan = planRelease(root, 'parche');
  publishRelease(root, plan, 'Corrección de prueba', { dryRun: true });
  assert.equal(fs.readFileSync(path.join(root, 'VERSION'), 'utf8'), '1.0.0\n');
  assert.equal(git(root, 'status', '--short'), plan.status);
  assert.equal(git(root, 'rev-parse', 'HEAD'), plan.head);
  assert.equal(git(root, 'tag', '--list'), '');
  assert.equal(git(origin, 'tag', '--list'), '');
});

test('publica versión, cambios y tag anotado en el remoto temporal', t => {
  const { root, origin } = repository(t);
  fs.appendFileSync(path.join(root, 'app.py'), 'corrección\n');
  const plan = planRelease(root, 'parche');
  publishRelease(root, plan, 'Corrige la pausa');
  assert.equal(fs.readFileSync(path.join(root, 'VERSION'), 'utf8'), '1.0.1\n');
  assert.equal(git(root, 'status', '--short'), '');
  assert.equal(git(root, 'cat-file', '-t', plan.tag), 'tag');
  assert.match(git(root, 'for-each-ref', '--format=%(contents)', `refs/tags/${plan.tag}`), /Corrige la pausa/);
  assert.equal(git(origin, 'rev-parse', 'refs/heads/main'), git(root, 'rev-parse', 'HEAD'));
  assert.equal(git(origin, 'rev-parse', `${plan.tag}^{commit}`), git(root, 'rev-parse', 'HEAD'));
});

test('publica la versión inicial sin crear un commit vacío', t => {
  const { root, origin } = repository(t);
  const plan = planRelease(root, 'actual');
  publishRelease(root, plan, 'Primera versión');
  assert.equal(git(root, 'rev-parse', 'HEAD'), plan.head);
  assert.equal(git(origin, 'rev-parse', 'v1.0.0^{commit}'), plan.head);
});

test('rechaza tags duplicados y versiones anteriores a un tag remoto', t => {
  const { root } = repository(t);
  git(root, 'tag', 'v2.0.0');
  git(root, 'push', 'origin', 'v2.0.0');
  assert.throws(() => planRelease(root, 'parche'), /anterior al tag remoto/);
  fs.writeFileSync(path.join(root, 'VERSION'), '2.0.0\n');
  assert.throws(() => planRelease(root, 'actual'), /tag local/);
  git(root, 'tag', '-d', 'v2.0.0');
  assert.throws(() => planRelease(root, 'actual'), /ya existe en origin/);
});

test('un rechazo del tag no publica tampoco la rama', t => {
  const { root, origin } = repository(t);
  const hook = path.join(origin, 'hooks', 'pre-receive');
  fs.writeFileSync(hook, '#!/bin/sh\nwhile read old new ref; do\ncase "$ref" in refs/tags/*) exit 1;; esac\ndone\n');
  fs.chmodSync(hook, 0o755);
  const plan = planRelease(root, 'parche');
  assert.throws(() => publishRelease(root, plan, 'Prueba de rechazo'), /siguen locales/);
  assert.equal(git(origin, 'rev-parse', 'refs/heads/main'), plan.head);
  assert.equal(git(origin, 'tag', '--list'), '');
  assert.notEqual(git(root, 'rev-parse', 'HEAD'), plan.head);
  assert.equal(git(root, 'tag', '--list'), 'v1.0.1');
});

test('no publica si el checkout cambió o falta la descripción', t => {
  const { root } = repository(t);
  const plan = planRelease(root, 'parche');
  assert.throws(() => publishRelease(root, plan, ''), /descripción/);
  fs.writeFileSync(path.join(root, 'nuevo.py'), 'cambio después de revisar\n');
  assert.throws(() => publishRelease(root, plan, 'Descripción'), /checkout cambió/);
  assert.equal(fs.readFileSync(path.join(root, 'VERSION'), 'utf8'), '1.0.0\n');
});

test('rechaza HEAD separado y argumentos inválidos', t => {
  const { root } = repository(t);
  git(root, 'checkout', '--detach');
  assert.throws(() => planRelease(root, 'parche'), /HEAD separado/);
  assert.throws(() => parseArgs(['--kind']));
  assert.throws(() => parseArgs(['--forzar']));
  assert.deepEqual(parseArgs(['--dry-run', '--kind', 'parche']), { dryRun: true, kind: 'parche' });
});

test('rechaza una rama que no contiene el último commit remoto', t => {
  const { root } = repository(t);
  const tree = git(root, 'rev-parse', 'HEAD^{tree}');
  const remoteCommit = git(root, 'commit-tree', tree, '-p', 'HEAD', '-m', 'Cambio de otro equipo');
  git(root, 'push', 'origin', `${remoteCommit}:refs/heads/main`);
  assert.throws(() => planRelease(root, 'parche'), /Sincroniza la rama/);
  assert.equal(fs.readFileSync(path.join(root, 'VERSION'), 'utf8'), '1.0.0\n');
});

test('un hook que cambia VERSION no permite publicar un tag incorrecto', t => {
  const { root, origin } = repository(t);
  const hook = path.join(root, '.git', 'hooks', 'pre-commit');
  fs.writeFileSync(hook, '#!/bin/sh\nprintf "9.9.9\\n" > VERSION\ngit add VERSION\n');
  fs.chmodSync(hook, 0o755);
  const plan = planRelease(root, 'parche');
  assert.throws(() => publishRelease(root, plan, 'Prueba de hook'), /VERSION esperada/);
  assert.equal(git(origin, 'rev-parse', 'refs/heads/main'), plan.head);
  assert.equal(git(origin, 'tag', '--list'), '');
});

function publication(t) {
  const { root } = repository(t);
  const plan = planRelease(root, 'parche');
  publishRelease(root, plan, 'Prueba de publicación completa');
  const repo = 'example/workBreak';
  const build = { databaseId: 123, event: 'push', headBranch: plan.tag,
    url: `https://github.com/${repo}/actions/runs/123` };
  const release = { tag_name: plan.tag, draft: false, prerelease: false,
    html_url: `https://github.com/${repo}/releases/tag/${plan.tag}`,
    assets: ['arm64', 'x86_64'].flatMap(arch => [
      { name: `WorkBreak-${plan.target}-macos-${arch}.dmg`, state: 'uploaded' },
      { name: `WorkBreak-macos-${arch}.dmg`, state: 'uploaded' },
    ]) };
  const calls = [];
  const run = (_cwd, args) => {
    calls.push(args);
    if (args[0] === 'run' && args[1] === 'list') return JSON.stringify([build]);
    if (args[0] === 'api') return JSON.stringify(release);
    return '';
  };
  return { root, plan, repo, build, release, calls, run };
}

test('comprueba gh y acceso a Actions antes de modificar Git', () => {
  const calls = [];
  assert.equal(prepareGitHub('/checkout', (_cwd, args) => {
    calls.push(args);
    return args[0] === 'repo' ? JSON.stringify({ nameWithOwner: 'example/workBreak' }) : '{}';
  }), 'example/workBreak');
  assert.equal(calls.length, 3);
  assert.throws(() => prepareGitHub('/checkout', () => { throw new Error('gh no disponible'); }),
    /No se han creado commits ni tags/);
});

test('espera el workflow del push y comprueba los cuatro DMG sin duplicar la ejecución', async t => {
  const p = publication(t);
  assert.deepEqual(await completeRelease(p.root, p.plan, p.repo, { run: p.run, attempts: 1 }), p.release);
  assert.ok(p.calls.some(args => args[0] === 'run' && args[1] === 'watch' && args.includes('--exit-status')));
  assert.ok(!p.calls.some(args => args[0] === 'workflow'));
});

test('inicia automáticamente el workflow si el push no lo activó', async t => {
  const p = publication(t);
  let dispatched = false;
  const run = (cwd, args) => {
    if (args[0] === 'run' && args[1] === 'list' && !dispatched) return '[]';
    if (args[0] === 'workflow') dispatched = true;
    return p.run(cwd, args);
  };
  await completeRelease(p.root, p.plan, p.repo, { run, attempts: 1 });
  const dispatch = p.calls.find(args => args[0] === 'workflow');
  assert.ok(dispatch.includes(p.plan.tag));
  assert.ok(dispatch.includes(`tag=${p.plan.tag}`));
});

test('ignora ejecuciones de otro tag incluso si comparten commit', async t => {
  const p = publication(t);
  p.build.headBranch = 'v9.9.9';
  await assert.rejects(completeRelease(p.root, p.plan, p.repo, { run: p.run, attempts: 1 }),
    /no registró la compilación/);
});

test('un fallo de Actions no se anuncia como publicación disponible', async t => {
  const p = publication(t);
  const run = (cwd, args) => {
    if (args[0] === 'run' && args[1] === 'watch') throw new Error('Workflow fallido');
    return p.run(cwd, args);
  };
  await assert.rejects(completeRelease(p.root, p.plan, p.repo, { run, attempts: 1 }), /falló/);
  assert.ok(!p.calls.some(args => args[0] === 'api'));
});

test('rechaza Release en borrador, prerelease, de otro tag o con DMG sin subir', async t => {
  const p = publication(t);
  for (const cambio of [{ draft: true }, { prerelease: true }, { tag_name: 'v9.9.9' },
    { assets: p.release.assets.slice(1) },
    { assets: p.release.assets.map(asset => ({ ...asset, state: 'new' })) }]) {
    const run = (cwd, args) => args[0] === 'api'
      ? JSON.stringify({ ...p.release, ...cambio }) : p.run(cwd, args);
    await assert.rejects(completeRelease(p.root, p.plan, p.repo, { run, attempts: 1 }), /no está publicada/);
  }
});
