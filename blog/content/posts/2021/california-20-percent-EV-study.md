---
title: "Разбор калифорнийского исследования про лояльность владельцев EV"
date: 2021-11-18T18:39:09+01:00
tags:
  - Автомобили
summary: Разбор нашумевшего в СМИ исследования Университета Калифорнии о возврате 21% владельцев электромобилей обратно к ДВС.
---

Несколько месяцев назад в СМИ нашумела работа группы из Университета Калифорнии [Discontinuance among California’s electric vehicle buyers: Why are some consumers abandoning their electric vehicles?](https://escholarship.org/uc/item/11n6f4hs), целью которой было изучение причин, по которым владельцы "чистых" автомобилей (на батареях - BEV, водородных топливных ячейках - FCEV и подключаемые гибриды - PHEV) от них отказываются и возвращаются обратно к "грязным" ДВС.

Для получения этой информации было опрошено почти 5 тыс владельцев автомобилей в Калифорнии о сроках владения автомобилем, демографических данных, наличии зарядного устройства дома, дальних поездках и т.п. Опрошенные владельцы приобрели автомобили с 2013 по 2018 годы; опрос проводился в 2019 году. 

В процессе работы с данными в числе прочего была получена интересная цифра: около 20% владельцев "новых" автомобилей возвращаются к "старым" ДВС. Эта цифра меня несколько удивила, так как мой личный опыт общения с электроводами говорит об обратном: редкий водитель согласится покупать ДВС после езды на электричке, так что давайте разберемся, что же на самом деле говорят исходные данные работы ([они свободно доступны](https://datadryad.org/stash/dataset/doi:10.25338/B8WS6R)).

```python
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
sns.set(style="darkgrid")

data = pd.read_excel("Discontinaunce_of_PEVs_in_California_Data_2021.03.01.xlsx")
```

## Сменившие авто

Один из ключевых моментов работы - тот факт, что исследователей интересовали только владельцы, которые **уже поменяли** свой автомобиль на новый, таким образом, проголосовав "за" или "против" электричек кошельком, так что давайте отбросим данные владельцев, которые продолжают пользоваться старым автомобилем. 

```python
changed = data[data["[s] Discontinuance (inc. purchased lease) 2"] != "Original"]
changed["Continued"] = changed["[s] Discontinuance (inc. purchased lease) 2"].map(lambda c: c == "Continued" and 1 or 0)
```

```python
fig = sns.histplot(changed[changed["Continued"] == 1]["[s] Electric driving range"], color="g")
fig = sns.histplot(changed[changed["Continued"] == 0]["[s] Electric driving range"], color="r")
plt.show()
```

![Распределение "за" и "против"](/images/output_4_0.png)
    
Явно заметно разделение рынка на две группы. Первая - до 150 миль хода (это PHEV и т.н. "compliance cars"), вторая - свыше 150 миль (это FCEV и всякие Теслы). Давайте посчитаем процент "отказников" для каждой из этих групп отдельно:


```python
phevs = changed[changed["oldcartype. {TOKEN:ATTRIBUTE_2} 2"] == "PHEV"]
len(phevs[phevs["Continued"] == 0]) / len(phevs)
```




    0.2165206508135169




```python
evs = changed[changed["oldcartype. {TOKEN:ATTRIBUTE_2} 2"] == "BEV"]
compliance = evs[evs["[s] Electric driving range"] < 150]
len(compliance[compliance["Continued"] == 0]) / len(compliance)
```




    0.22209944751381216




```python
fcevs = changed[changed["oldcartype. {TOKEN:ATTRIBUTE_2} 2"].isnull()]
len(fcevs[fcevs["Continued"] == 0]) / len(fcevs)
```




    0.6097560975609756




```python
teslas = evs[evs["[s] Electric driving range"] >= 150]
len(teslas[teslas["Continued"] == 0]) / len(teslas)
```




    0.09852216748768473



```python
len(changed[changed["Continued"] == 0]) / len(changed)
```



    0.21498204207285787


И логичным образом, в выводах исследователей "лояльность" тут коррелирует с наличием зарядки дома, длительных поездок и т.п.

## По всем водителям

А теперь - представим, что нам не нужно выяснять причины "лояльности", а лишь понять, насколько владельцы автомобилей "нового поколения" ими довольны. Для этого возьмем все данные, включая тех водителей, кто продолжает ездить на своем старом автомобиле (если бы они были им недовольны - они бы его сменили).


```python
data["Continued"] = data["[s] Discontinuance (inc. purchased lease) 2"].map(lambda c: c in ["Continued", "Original"] and 1 or 0)
```


```python
fig = sns.histplot(data[data["Continued"] == 1]["[s] Electric driving range"], color="g")
fig = sns.histplot(data[data["Continued"] == 0]["[s] Electric driving range"], color="r")
plt.show()
```


    
![Распределение "за" и "против"](/images/output_12_0.png)
    



```python
phevs = data[data["oldcartype. {TOKEN:ATTRIBUTE_2} 2"] == "PHEV"]
len(phevs[phevs["Continued"] == 0]) / len(phevs)
```




    0.0857709469509172




```python
evs = data[data["oldcartype. {TOKEN:ATTRIBUTE_2} 2"] == "BEV"]
compliance = evs[evs["[s] Electric driving range"] < 150]
len(compliance[compliance["Continued"] == 0]) / len(compliance)
```




    0.14105263157894737




```python
fcevs = data[data["oldcartype. {TOKEN:ATTRIBUTE_2} 2"].isnull()]
len(fcevs[fcevs["Continued"] == 0]) / len(fcevs)
```




    0.15432098765432098




```python
teslas = evs[evs["[s] Electric driving range"] >= 150]
len(teslas[teslas["Continued"] == 0]) / len(teslas)
```




    0.016260162601626018



```python
len(data[data["Continued"] == 0]) / len(data)
```



    0.08665977249224405





Итак, по исходной методике имеем:

* FCEV: 60.9% "отказников"
* BEV с малым запасом хода: 22.2% 
* PHEV: 21.6%
* BEV с достаточным запасом хода: 9.8%
* Итого: 21.5%

По всем водителям:

* FCEV: 15.4% "отказников"
* BEV с малым запасом хода: 14.1% 
* PHEV: 8.5%
* BEV с достаточным запасом хода: 1.6%
* Итого: 8.7%

## Выводы:

Если считать статистику по всем водителям, что логичнее для оценки уровня лояльности, получаем **8.7%** "отказников", что уже более чем вдвое ниже распиаренной цифры в 21%. 

Причем, бОльшая их часть -

* FCEV, инфраструктура для которых даже в Калифорнии до сих пор в зачаточном состоянии, а в соседних штатах - вовсе отсутствует
* Compliance cars, которые изначально создавались не для массовых продаж и масштабной конкуренции с ДВС
* PHEV, которые часто покупаются как ДВС, без каких-либо изменений в паттернах использования, исключительно ради полагающихся субсидий штата (благодаря которым PHEV может оказаться дешевле "обычного" гибрида). 

Среди же всех владельцев BEV с приемлемым запасом хода (от 150 миль, 241 км) отказались от электротяги всего **1.6%** владельцев. 