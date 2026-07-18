function TodoRow({ todo }) {
  return (
    <li className="todo">
      <span className={`pill state-${todo.state}`}>{todo.state}</span>
      <span className="todo-title">{todo.title}</span>
      <span className="todo-tags">
        {todo.context && <span className="tag context">{todo.context}</span>}
        {todo.area && <span className="tag area">{todo.area}</span>}
        {todo.waiting_on && <span className="tag waiting">{todo.waiting_on}</span>}
      </span>
    </li>
  )
}

export default function TodoList({ todos }) {
  if (todos.length === 0) {
    return <p className="empty">Nothing here.</p>
  }
  return (
    <ul className="todo-list">
      {todos.map((todo) => (
        <TodoRow key={todo.id} todo={todo} />
      ))}
    </ul>
  )
}
