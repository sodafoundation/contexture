# ClickHouse Agentic Copilot Test Report



## Application

E-commerce Dataset



## OCS Schema



### customers

Fields:

- customer_id

- name

- email

- city



### products

Fields:

- product_id

- name

- category

- price

- stock



### orders

Fields:

- order_id

- customer_id

- product_id

- quantity

- order_date



## Relationships



customers → orders → products



## Test Cases



### Test 1: ClickHouse Connection

PASS



### Test 2: Tables Loaded

PASS



### Test 3: Relationship Query



Query:

What products did Rahul buy?



Output:

Rahul bought Laptop, Mouse



PASS



### Test 4: All Customer-Product Relationships



| Customer | Product    | Category    | Qty | Unit Price | Total Amount |
|----------|------------|-------------|-----|------------|--------------|
| Amit     | Notebook   | Stationery  |   5 |     200.00 |      1000.00 |
| Priya    | Keyboard   | Electronics |   1 |    3000.00 |      3000.00 |
| Priya    | Headphones | Electronics |   1 |    5000.00 |      5000.00 |
| Rahul    | Laptop     | Electronics |   1 |   75000.00 |     75000.00 |
| Rahul    | Mouse      | Electronics |   2 |    1500.00 |      3000.00 |
| Sneha    | Laptop     | Electronics |   1 |   75000.00 |     75000.00 |
| Vikram   | Mouse      | Electronics |   3 |    1500.00 |      4500.00 |

PASS



## Conclusion



OCS schema verified successfully.

Relationship traversal and context-aware query execution are working correctly.
