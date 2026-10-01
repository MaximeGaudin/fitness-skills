var BLOCK_COUNT = BLOCK_NAMES.length;
var currentBlock = 0;

var blockNameEl = document.getElementById("block-name");
var btnPrev = document.getElementById("btn-prev");
var btnNext = document.getElementById("btn-next");

function showBlock(idx) {
  var i;
  for (i = 0; i < BLOCK_COUNT; i++) {
    var el = document.getElementById("block-" + i);
    if (el) el.style.display = (i === idx) ? "" : "none";
  }
  var doneEl = document.getElementById("block-done");
  if (doneEl) doneEl.style.display = (idx >= BLOCK_COUNT) ? "" : "none";
}

function updateDots() {
  var i;
  for (i = 0; i < BLOCK_COUNT; i++) {
    var dot = document.getElementById("dot-" + i);
    if (!dot) continue;
    if (i < currentBlock) {
      dot.className = "progress-dot-done";
    } else if (i === currentBlock) {
      dot.className = "progress-dot-active";
    } else {
      dot.className = "progress-dot";
    }
  }
}

function loadBlock(idx) {
  if (idx >= BLOCK_COUNT) {
    currentBlock = idx;
    if (blockNameEl) blockNameEl.innerHTML = "DONE";
    showBlock(idx);
    updateDots();
    if (btnPrev) btnPrev.style.visibility = "visible";
    return;
  }
  currentBlock = idx;
  if (blockNameEl) blockNameEl.innerHTML = BLOCK_NAMES[idx];

  if (BLOCK_HAS_VIDEO[idx]) {
    var vframe = document.getElementById("video-frame-" + idx);
    if (vframe && !vframe.src && vframe.getAttribute("data-src")) {
      vframe.src = vframe.getAttribute("data-src");
    }
  }

  showBlock(idx);
  updateDots();
  if (btnPrev) btnPrev.style.visibility = (idx > 0) ? "visible" : "hidden";
}

function timerNext() {
  loadBlock(currentBlock + 1);
}

function timerPrev() {
  if (currentBlock > 0) {
    loadBlock(currentBlock - 1);
  }
}

document.onkeydown = function(e) {
  var key = e.keyCode || e.which;
  if (key === 39) timerNext();
  if (key === 37) timerPrev();
};

loadBlock(0);

(function initClock() {
  var el = document.getElementById("top-clock");
  if (!el) return;
  function tick() {
    var now = new Date();
    var h = now.getHours();
    var m = now.getMinutes();
    el.textContent = (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }
  tick();
  setInterval(tick, 10000);
})();
