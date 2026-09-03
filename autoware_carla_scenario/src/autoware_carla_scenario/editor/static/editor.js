/* Scenario Editor -- the small amount of behaviour that is genuinely client-side.
 *
 * Everything that changes the scenario goes through htmx and a server render, so
 * this file is limited to what a server cannot do: drawing the connector lines
 * between a trigger and the action it fires, moving the keyboard focus around
 * the swimlanes, and toggling the export panel.
 */
(function () {
  'use strict';

  /* ---------------------------------------------------------------------
   * DAG connectors
   *
   * Each trigger block is linked to its action card. The line is drawn into
   * one SVG overlay positioned over the canvas, so adding a predicate never
   * has to reason about layout -- it just re-renders and we redraw.
   * ------------------------------------------------------------------- */

  function drawLinks() {
    var canvas = document.getElementById('canvas');
    if (!canvas) return;
    var scroll = canvas.querySelector('.ed-canvas-scroll');
    var svg = canvas.querySelector('.ed-links');
    if (!scroll || !svg) return;

    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute('width', scroll.scrollWidth);
    svg.setAttribute('height', scroll.scrollHeight);

    var origin = scroll.getBoundingClientRect();
    var wraps = scroll.querySelectorAll('.ed-trigger-wrap[data-links-to]');

    wraps.forEach(function (wrap) {
      var target = document.getElementById(wrap.getAttribute('data-links-to'));
      if (!target) return;
      var trigger = wrap.querySelector('.ed-trigger');
      if (!trigger) return;

      var from = trigger.getBoundingClientRect();
      var to = target.getBoundingClientRect();

      var x1 = from.left + from.width / 2 - origin.left + scroll.scrollLeft;
      var y1 = from.top - origin.top + scroll.scrollTop;
      var x2 = to.left + to.width / 2 - origin.left + scroll.scrollLeft;
      var y2 = to.bottom - origin.top + scroll.scrollTop;
      if (y1 <= y2) return; // trigger is not below its action; nothing to draw

      var mid = (y1 + y2) / 2;
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute(
        'd',
        'M ' + x1 + ' ' + y1 + ' C ' + x1 + ' ' + mid + ', ' + x2 + ' ' + mid + ', ' + x2 + ' ' + y2
      );
      svg.appendChild(path);

      var head = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      head.setAttribute(
        'd',
        'M ' + x2 + ' ' + y2 + ' l -4 5 l 8 0 z'
      );
      head.setAttribute('class', 'head');
      svg.appendChild(head);
    });
  }

  var redrawTimer = null;
  function scheduleRedraw() {
    if (redrawTimer) window.clearTimeout(redrawTimer);
    redrawTimer = window.setTimeout(drawLinks, 30);
  }

  /* ---------------------------------------------------------------------
   * Selection and keyboard navigation
   *
   * Cards carry data-object-id and their own hx-get, so selecting is just
   * "activate the element". Arrow keys walk the selectable cards in document
   * order, which follows the swimlanes left to right, top to bottom.
   * ------------------------------------------------------------------- */

  function selectable() {
    return Array.prototype.slice.call(
      document.querySelectorAll('#canvas [data-object-id]')
    );
  }

  function focusOffset(delta) {
    var nodes = selectable();
    if (!nodes.length) return;
    var index = nodes.indexOf(document.activeElement);
    var next = nodes[Math.max(0, Math.min(nodes.length - 1, (index < 0 ? 0 : index + delta)))];
    if (next) {
      next.focus();
      if (window.htmx) window.htmx.trigger(next, 'click');
    }
  }

  document.addEventListener('keydown', function (event) {
    if (event.target && /^(INPUT|SELECT|TEXTAREA)$/.test(event.target.tagName)) return;

    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
      focusOffset(1);
      event.preventDefault();
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
      focusOffset(-1);
      event.preventDefault();
    } else if (event.key === 'Enter' || event.key === ' ') {
      var active = document.activeElement;
      if (active && active.hasAttribute('data-object-id')) {
        if (window.htmx) window.htmx.trigger(active, 'click');
        event.preventDefault();
      }
    } else if (event.key === 'Escape') {
      var panel = document.getElementById('export-panel');
      if (panel) panel.classList.add('hidden');
    }
  });

  /* ---------------------------------------------------------------------
   * Export panel
   * ------------------------------------------------------------------- */

  window.toggleExportPanel = function () {
    var panel = document.getElementById('export-panel');
    if (panel) panel.classList.toggle('hidden');
  };

  /* ---------------------------------------------------------------------
   * Wiring
   * ------------------------------------------------------------------- */

  document.addEventListener('DOMContentLoaded', scheduleRedraw);
  document.body.addEventListener('htmx:afterSwap', scheduleRedraw);
  document.body.addEventListener('htmx:afterSettle', scheduleRedraw);
  window.addEventListener('resize', scheduleRedraw);
  scheduleRedraw();
})();
