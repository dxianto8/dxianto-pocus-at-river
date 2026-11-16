(() => {
  const update = () => {
    const eventType = document.getElementById('id_event_type')?.value;
    document.querySelectorAll('[data-event-types]').forEach(input => {
      const types = input.dataset.eventTypes.split(',').filter(Boolean);
      const applies = !types.length || types.includes(eventType);
      input.closest('.field').hidden = !applies;
      input.disabled = !applies;
      input.required = applies && input.dataset.questionRequired === 'true';
    });
  };
  document.addEventListener('change', event => {
    if (event.target.id === 'id_event_type') update();
  });
  window.pocusQuestionnaire = update;
  update();
})();
