/**
 * Helper function to bind click event listener and update counter count in target element.
 * 
 * @param {HTMLElement} element - Target HTML element to mount click counter on.
 */
export function setupCounter(element) {
  let counter = 0
  const setCounter = (count) => {
    counter = count
    element.innerHTML = `Count is ${counter}`
  }
  element.addEventListener('click', () => setCounter(counter + 1))
  setCounter(0)
}

