import os
import json
import time
from scripts.map_reduce_refine import reduce_results

def test_reduce_real():
    """Тестирование REDUCE-фазы с реальными данными"""
    # Находим последний файл с тестовыми данными
    reduce_test_dirs = [d for d in os.listdir("./output") if d.startswith("reduce_test_")]
    reduce_test_dirs.sort(reverse=True)
    
    if not reduce_test_dirs:
        print("Не найдены тестовые данные для REDUCE-фазы")
        return
    
    # Загружаем тестовые данные
    latest_dir = os.path.join("./output", reduce_test_dirs[0])
    map_outputs_path = os.path.join(latest_dir, "map_outputs.json")
    
    print(f"Загрузка тестовых данных из: {map_outputs_path}")
    with open(map_outputs_path, "r", encoding="utf-8") as f:
        map_outputs = json.load(f)
    
    # Выводим статистику входных данных
    decisions_count = sum(len(segment.get("decisions", [])) for segment in map_outputs)
    actions_count = sum(len(segment.get("actions", [])) for segment in map_outputs)
    
    print(f"\nИсходные данные:")
    print(f"  Количество сегментов: {len(map_outputs)}")
    print(f"  Всего решений: {decisions_count}")
    print(f"  Всего задач: {actions_count}")
    
    # Запускаем REDUCE-фазу
    print("\nЗапуск REDUCE-фазы...")
    start_time = time.time()
    reduced_data = reduce_results(map_outputs)
    end_time = time.time()
    
    execution_time = end_time - start_time
    print(f"REDUCE-фаза выполнена за {execution_time:.2f} секунд")
    
    # Выводим результаты REDUCE-фазы
    reduced_decisions = reduced_data.get("decisions", [])
    reduced_actions = reduced_data.get("actions", [])
    
    print(f"\nРезультаты REDUCE-фазы:")
    print(f"  Уникальных решений: {len(reduced_decisions)} (было {decisions_count})")
    print(f"  Уникальных задач: {len(reduced_actions)} (было {actions_count})")
    
    # Выводим уникальные решения
    print("\nУникальные решения:")
    for i, decision in enumerate(reduced_decisions):
        print(f"  {i+1}. {decision}")
    
    # Выводим уникальные задачи
    print("\nУникальные задачи:")
    for i, action in enumerate(reduced_actions):
        who = action.get("who", "Не указано")
        what = action.get("what", "Не указано")
        due = action.get("due", "Не указано")
        print(f"  {i+1}. Кто: {who}, Что: {what}, Срок: {due}")
    
    # Сохраняем результат REDUCE-фазы
    result_path = os.path.join(latest_dir, "reduced_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(reduced_data, f, ensure_ascii=False, indent=2)
    
    print(f"\nРезультат сохранен в: {result_path}")

if __name__ == "__main__":
    test_reduce_real()