let sid = null, qid = null, turn = 0, wrongGuesses = 0;
const MAX_WRONG = 3;
const el = () => document.getElementById('app');
const set = h => { el().innerHTML = h; };

function start() {
  set('<button class="wide" onclick="go()">Start Game</button>');
}

async function go() {
  turn = 0;
  wrongGuesses = 0;
  set('<p class="msg">Loading...</p>');
  const d = await post('/game/start', {});
  sid = d.session_id;
  qid = d.question_id;
  showQ(d.question_text);
}

function showQ(text) {
  turn++;
  set(`<div class="turn">Question ${turn}</div>
<p class="question">${text}</p>
<div class="answers">
  <button onclick="ans('yes')">Yes</button>
  <button onclick="ans('probably')">Probably</button>
  <button onclick="ans('maybe')">Maybe</button>
  <button onclick="ans('probably not')">Probably Not</button>
  <button onclick="ans('no')">No</button>
</div>`);
}

async function ans(v) {
  el().querySelectorAll('button').forEach(b => b.disabled = true);
  const d = await post('/game/answer', { session_id: sid, question_id: qid, answer: v });
  if (d.done) {
    showGuess(d.guess_name, d.confidence);
  } else {
    qid = d.next_question_id;
    showQ(d.next_question_text);
  }
}

function showGuess(name, conf) {
  const pct = Math.round(conf * 100);
  set(`<p class="question">Is it...</p>
<div class="guess-name">${name}</div>
<p class="conf">${pct}% confidence</p>
<div class="row">
  <button onclick="fb(true)">Yes</button>
  <button onclick="wrongGuess()">No</button>
</div>`);
}

async function fb(correct, correctName = null) {
  const body = { session_id: sid, was_correct: correct };
  if (correctName) body.correct_name = correctName;
  await post('/game/feedback', body);
  set(`<p class="question">${correct ? 'Got it!' : "I'll remember that."}</p>
<button class="wide" onclick="go()">Play Again</button>`);
}

async function wrongGuess() {
  wrongGuesses++;
  if (wrongGuesses >= MAX_WRONG) {
    giveUp();
    return;
  }
  set('<p class="msg">Let me think...</p>');
  const d = await post('/game/continue', { session_id: sid });
  if (d.detail) {
    giveUp();
    return;
  }
  qid = d.next_question_id;
  showQ(d.next_question_text);
}

function giveUp() {
  set(`<p class="question">I give up! Who were you thinking of?</p>
<input type="text" id="cname" placeholder="Name..."
  onkeydown="if(event.key==='Enter') sub()" />
<button class="wide" onclick="sub()">Submit</button>
<p class="err" id="err"></p>`);
  document.getElementById('cname').focus();
}

async function sub() {
  const name = document.getElementById('cname').value.trim();
  if (!name) { document.getElementById('err').textContent = 'Please enter a name'; return; }
  await fb(false, name);
}

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.json();
}

start();
