/* ===== Pomodoro Timer ===== */
let timerInterval = null;
let totalSeconds = 25 * 60;
let remainingSeconds = totalSeconds;
let running = false;

function updateDisplay() {
  const m = Math.floor(remainingSeconds / 60).toString().padStart(2, '0');
  const s = (remainingSeconds % 60).toString().padStart(2, '0');
  document.getElementById('timer-display').textContent = `${m}:${s}`;
}

function startTimer() {
  if (running) return;
  running = true;
  document.getElementById('start-btn').disabled = true;
  document.getElementById('pause-btn').disabled = false;
  timerInterval = setInterval(() => {
    if (remainingSeconds <= 0) {
      clearInterval(timerInterval);
      running = false;
      document.getElementById('start-btn').disabled = false;
      document.getElementById('pause-btn').disabled = true;
      alert('Time is up! Take a break 🎉');
      return;
    }
    remainingSeconds--;
    updateDisplay();
  }, 1000);
}

function pauseTimer() {
  clearInterval(timerInterval);
  running = false;
  document.getElementById('start-btn').disabled = false;
  document.getElementById('pause-btn').disabled = true;
}

function resetTimer() {
  pauseTimer();
  remainingSeconds = totalSeconds;
  updateDisplay();
}

function setMode(minutes, btn) {
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  totalSeconds = minutes * 60;
  remainingSeconds = totalSeconds;
  running = false;
  clearInterval(timerInterval);
  document.getElementById('start-btn').disabled = false;
  document.getElementById('pause-btn').disabled = true;
  updateDisplay();
}

/* ===== Flashcards ===== */
let cards = [
  { q: 'What is the capital of France?', a: 'Paris' },
  { q: 'What does HTML stand for?', a: 'HyperText Markup Language' },
  { q: 'What is 7 × 8?', a: '56' },
  { q: 'Who wrote Romeo and Juliet?', a: 'William Shakespeare' },
  { q: 'What is the speed of light (approx)?', a: '300,000 km/s' },
];
let cardIndex = 0;

function renderCard() {
  const card = cards[cardIndex];
  document.getElementById('card-question').textContent = card.q;
  document.getElementById('card-answer').textContent = card.a;
  document.getElementById('card-counter').textContent = `${cardIndex + 1} / ${cards.length}`;
  const fc = document.getElementById('flashcard');
  fc.classList.remove('flipped');
}

function flipCard() {
  document.getElementById('flashcard').classList.toggle('flipped');
}

function nextCard() {
  cardIndex = (cardIndex + 1) % cards.length;
  renderCard();
}

function prevCard() {
  cardIndex = (cardIndex - 1 + cards.length) % cards.length;
  renderCard();
}

function addCard() {
  const q = document.getElementById('new-question').value.trim();
  const a = document.getElementById('new-answer').value.trim();
  if (!q || !a) return;
  cards.push({ q, a });
  document.getElementById('new-question').value = '';
  document.getElementById('new-answer').value = '';
  cardIndex = cards.length - 1;
  renderCard();
}

/* ===== To-Do List ===== */
let todos = JSON.parse(localStorage.getItem('study-todos') || '[]');

function saveTodos() {
  localStorage.setItem('study-todos', JSON.stringify(todos));
}

function renderTodos() {
  const list = document.getElementById('todo-list');
  list.innerHTML = '';
  todos.forEach((todo, idx) => {
    const li = document.createElement('li');
    li.className = 'todo-item' + (todo.done ? ' done' : '');

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = todo.done;
    cb.addEventListener('change', () => {
      todos[idx].done = cb.checked;
      saveTodos();
      renderTodos();
    });

    const span = document.createElement('span');
    span.textContent = todo.text;

    const del = document.createElement('button');
    del.className = 'delete-btn';
    del.textContent = '✕';
    del.title = 'Delete';
    del.addEventListener('click', () => {
      todos.splice(idx, 1);
      saveTodos();
      renderTodos();
    });

    li.appendChild(cb);
    li.appendChild(span);
    li.appendChild(del);
    list.appendChild(li);
  });
}

function addTodo() {
  const input = document.getElementById('todo-input');
  const text = input.value.trim();
  if (!text) return;
  todos.push({ text, done: false });
  saveTodos();
  renderTodos();
  input.value = '';
}

/* ===== Notes (auto-save) ===== */
const notesArea = document.getElementById('notes-area');
notesArea.value = localStorage.getItem('study-notes') || '';
notesArea.addEventListener('input', () => {
  localStorage.setItem('study-notes', notesArea.value);
});

/* ===== Init ===== */
renderCard();
renderTodos();
