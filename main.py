import numpy as np
import networkx as nx


def sens_sort(graph):
    return sorted(graph, key=lambda x: nx.dijkstra_path_length(graph, x, 0,))


def route_structure(routes_list):
    for i, sens_route in enumerate(routes_list):
        if len(sens_route):
            for j, msg in enumerate(sens_route):
                routes_list[i][j] = [msg, (i,)]


def routes_create(graph, sens_buf=list(), balance = False):
    """
    Создает структуру данных для путей вида: [сенсор_i:[сообщение_j:[путь до бс:[], источник сообщения:(i,)]]]
    если параметр balance = True, то
    пытается найти наилучший путь для каждого сообщения в сенсорной сети изменяя веса ребер
    :param graph: граф сенсорной сети построенный с помощью networkx
    :return: список передач для каждого сенсора
    """
    sens_num = len(graph)
    if not sens_buf:
        sens_buf = [0 if i == 0 else 1 for i in range(sens_num)]

    if balance:
        routes_p_node = np.zeros((sens_num,), dtype=np.int)
        routes = [[] for _ in range(sens_num)]
        for i in sens_sort(graph):
            if i is not 0 or sens_buf[i]:
                for msg in range(sens_buf[i]):
                    routes[i].append(nx.dijkstra_path(graph, 0, i))

                    routes_p_node[routes[i][msg]] += 1
                    routes_p_node[0] = 0
                    for j in routes[i][msg]:
                        for e_num in graph[j]:
                            graph[j][e_num]['weight'] += routes_p_node[j] * sens_num ** -2
                            graph[e_num][j]['weight'] += routes_p_node[j] * sens_num ** -2
    else:
        routes = [[nx.dijkstra_path(graph, 0, i)] for i in graph]

    route_structure(routes)

    return routes


def rasp_create(adj_matrix, sens_buf=list(), balance=False):
    """
    Функция для составления расписания передачи сообщений от передатчиков к Базовой Станции (БС) в случайно
    связанной сети.

    :adj_matrix: Матрица смежности. лист листов с описанием связей графового представления системы.
    :balance: Бинарная опция включения/отключения балансировки
    :return: длину расписания, максимальное количество сообщений которые могут уйти из фрейма
    """

    # frame- Массив слотов, в каждом слоте указаны все сенсоры, сообщения которых были переданы на БС
    # example:  [[1,2],[4], ...]
    frame = []
    # num_req_to_exit = [0] * len(adj_matrix)
    # frame_len = 0
    sens_num = len(adj_matrix)  # Число передатчиков
    if not sens_buf:
        sens_buf = [0 if i == 0 else 1 for i in range(sens_num)]  # Количество сообщений на БС
    graph = nx.from_numpy_matrix(np.matrix(adj_matrix))

    trans_routes = routes_create(graph, sens_buf, balance)

    while any(sens_buf[1:]):  # Пока все заявки не попадут на БС,...
        # Список передач за слот
        trans_lock = [False] * sens_num  # Список заблокированных для передачи передатчиков
        receive_lock = [False] * sens_num  # Список заблокированных для приёма  передатчиков
        frame.append([])
        # В цикле исключена возможность передачи сообщения из БС (т.к. начинаем с 1)
        # Проходимся по сенсорам, проверяем возможность передачи и передаём
        for i in sens_sort(graph)[1:]:
            # берем сообщение из i-го сенсора, если есть
            if trans_routes[i]:
                message_route = trans_routes[i][0]
            else:
                continue
            # Проверка возможности передачи сообщения
            if len(message_route) > 1 and sens_buf[i] > 0:
                source = message_route[0][-1]  # откуда передавать
                receive = message_route[0][-2]  # куда передавать

                # Проверка возможности передачи сообщения
                trans_allowed = True
                if trans_lock[source] or receive_lock[receive]:
                    trans_allowed = False
                if trans_allowed:
                    # Добавление новой передачи в слот
                    # Блокировка на передачу и прием ближайших передатчиков
                    receive_lock = [True if neighbor == 1 or j == source
                                    else receive_lock[j]
                                    for j, neighbor in enumerate(adj_matrix[source])]

                    trans_lock = [True if neighbor == 1 or j == receive
                                  else trans_lock[j]
                                  for j, neighbor in enumerate(adj_matrix[receive])]

                    trans_lock[receive] = True
                    trans_lock[source] = True
                    sens_buf[receive] += 1
                    sens_buf[source] -= 1

                    message_route[0].pop()
                    if len(message_route[0]) == 1:
                        # num_req_to_exit[message_route[1][0]] += 1
                        frame[-1].append(message_route[1][0])
                    route = trans_routes[source].pop(trans_routes[source].index(message_route))
                    trans_routes[receive].append(route)

        # frame_len += 1
    return frame  # , num_req_to_exit   #result_way


def sens_graph_with_prob(adj, prb=None, num_of_frames=1000, adaptation=0):
    """
    Моделирует буфер сенсоров в сенорной сети

    :adj: Матрица смежности сенсорной сети
    :sch: Расписание работы сенсорной сети
    :prb: Вероятность появления сообщения в кажом слоте для всех сенсоров
    :num_of_frames: Количество фреймов для моделирования сенсорной сети
    :adaptation: Изменять ли расписание на каждом фрейме
    :return: среднее количество сообщений в буфере каждого сенсора
    """
    assert type(prb) is float or 0 <= prb <= 1

    # сообщения которые уйдут, но еще в системе
    sensors_out = [1 if i > 0 else 0 for i in range(len(adj))]
    sensors_in = [0 for _ in range(len(adj))]  # сообщения которые придут на слоте
    frame = rasp_create(adj_matrix=adj, balance=True)
    avg_buff, slot_num, frame_num, new_frame = 0, 0, 0, False

    # количество пришедших сообщений в слот
    count_come = np.random.binomial(1, prb, size=[1000000, len(adj)-1])

    for total_slots, slot_income in enumerate(count_come):  # общее количество слотов, сообщения на каждый сенсор

        sensors_in = [0 if i == 0 else sensors_in[i]+slot_income[i-1] for i in range(len(adj))]
        
        # print(frame)
        if frame:
            sensors_out = [sens-1 if i in frame[slot_num] and sens > 0 else sens for i, sens in enumerate(sensors_out)]

        avg_buff += sum(sensors_in)+sum(sensors_out)
        slot_num += 1
        if slot_num >= len(frame):
            # в конце фрейма все приходящие сообщения становятся уходящими на следующем слоте,
            # а все приходящие обнуляются
            sensors_out = [sensors_in[k] + sensors_out[k] for k in range(len(sensors_in))]
            sensors_in = [0 for i, _ in enumerate(range(len(adj)))]
            slot_num, new_frame = 0, True
            frame_num += 1

        if frame_num > num_of_frames:
            break

        if adaptation > 0 and new_frame is True:
            if frame_num % adaptation == 0:
                frame = rasp_create(adj_matrix=adj, sens_buf=sensors_out[:], balance=True)
                new_frame = False

    avg_buff /= total_slots

    return avg_buff


def show_graph(graph):
    """
    Функция для отображения графа

    :graph: матрица смежности (лист листов) или объект графа из библиотеки networkX
    :return: None
    """
    import matplotlib.pyplot as plt

    if type(graph) == list:
        graph = nx.from_numpy_matrix(np.matrix(graph))
    nx.draw_networkx(graph, with_labels=True)
    plt.show()


if __name__ == "__main__":
    from interactive_console import interactive_console
    adjacency_matrix = interactive_console()
    rasp_create(adjacency_matrix, sens_buf=[0, 2, 3, 0, 0, 0, 0, 0, 0], balance=True)
#     print(sens_graph_with_prob(adjacency_matrix, prb=0.126, num_of_frames=1000, adaptation=True))
