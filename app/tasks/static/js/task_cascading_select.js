// app/tasks/static/js/task_cascading_select.js

// Используем django.jQuery для обеспечения совместимости с админкой.
django.jQuery(document).ready(function() {
    
    // Определяем jQuery как $ для удобства внутри этой функции
    var $ = django.jQuery;
    
    // 1. Определяем селекторы по ID
    var $modelSelect = $('#id_oes_model');
    var $objectSelect = $('#id_oes_object');
    
    // URL для AJAX-запроса
    var loadObjectsUrl = '/tasks/ajax/load-objects/'; 
    
    // Переменная для хранения ID объекта при редактировании
    var currentObjectId = $objectSelect.val(); 

    function loadObjects() {
        var modelId = $modelSelect.val();

        // 🚨 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: 
        // Если modelId пуст (null, undefined, "", 0), отключаем, очищаем и выходим.
        if (!modelId || modelId === "" || modelId === "0") {
            $objectSelect.empty();
            $objectSelect.append($('<option value="">---------</option>'));
            $objectSelect.prop('disabled', true);
            return; 
        }

        // Запускаем загрузку
        $objectSelect.prop('disabled', true);
        $objectSelect.empty();
        $objectSelect.append($('<option value="">Загрузка...</option>'));

        $.ajax({
            url: loadObjectsUrl,
            data: {
                'oes_model': modelId // Передаем ID выбранной модели
            },
            dataType: 'json',
            success: function (data) {
                $objectSelect.empty();
                $objectSelect.append($('<option value="">---------</option>'));
                
                // Заполняем полученными объектами
                $.each(data.objects, function (index, obj) {
                    $objectSelect.append(
                        $('<option></option>').val(obj.id).text(obj.name)
                    );
                });
                
                // Восстанавливаем ранее выбранное значение при редактировании
                if (currentObjectId) {
                    if ($objectSelect.find('option[value="' + currentObjectId + '"]').length > 0) {
                        $objectSelect.val(currentObjectId);
                    }
                    currentObjectId = null; 
                }
                
                // Включаем поле для выбора
                $objectSelect.prop('disabled', false);
            },
            error: function(xhr, status, error) {
                console.error("Ошибка при загрузке OES Объектов:", error);
                $objectSelect.empty();
                $objectSelect.append($('<option value="">Ошибка загрузки</option>'));
                $objectSelect.prop('disabled', true);
            }
        });
    }

    // --- Инициализация и привязка событий ---
    
    // Привязываем функцию к событию изменения (change) поля Модели
    $modelSelect.on('change select2:select', loadObjects);

    // 🚨 КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ИНИЦИАЛИЗАЦИИ: 
    // Запускаем loadObjects при загрузке. Если модели нет, он сам отключит поле.
    loadObjects(); 
});