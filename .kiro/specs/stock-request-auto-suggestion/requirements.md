# Requirements Document

## Introduction

This feature enhances the Kitchen Portal's Stock Request functionality by automatically suggesting ingredients from the Kitchen Pantry that need to be restocked. Currently, kitchen staff must manually check the Kitchen Pantry to identify which ingredients are running low before creating stock requests. This feature will automatically display ingredients that are at critical levels (0 stock, critical level, or low stock) on the Stock Request page, streamlining the restocking process and reducing the time needed to create inventory requests.

## Glossary

- **Kitchen_Portal**: The web interface used by kitchen staff to manage orders, recipes, and stock requests
- **Stock_Request_Page**: The page at `/staff/kitchen/stock-requests` where kitchen staff create and view stock requests
- **Kitchen_Pantry**: The on-hand inventory at the kitchen, tracked via the `kitchen_qty` field in the Ingredient model
- **Main_Inventory**: The warehouse/bodega inventory tracked via the `stock_qty` field in the Ingredient model
- **Ingredient**: A raw material or component used in menu items, with both kitchen and warehouse quantities
- **Auto_Suggestion_System**: The system component that identifies and displays ingredients needing restock
- **Critical_Level**: An ingredient with `kitchen_qty` equal to 0 (out of stock)
- **Low_Level**: An ingredient with `kitchen_qty` greater than 0 but less than or equal to `reorder_level`
- **Reorder_Level**: The threshold quantity below which an ingredient is considered low stock
- **Stock_Request**: A formal request from kitchen staff to transfer ingredients from Main_Inventory to Kitchen_Pantry

## Requirements

### Requirement 1: Display Auto-Suggested Ingredients

**User Story:** As a kitchen staff member, I want to see ingredients that are at critical or low levels automatically displayed on the Stock Request page, so that I can quickly identify what needs to be restocked without manually checking the Kitchen Pantry.

#### Acceptance Criteria

1. WHEN a kitchen staff member accesses the Stock_Request_Page, THE Auto_Suggestion_System SHALL retrieve all Ingredients where `kitchen_qty` is less than or equal to `reorder_level`
2. THE Auto_Suggestion_System SHALL categorize retrieved Ingredients into three groups: Critical_Level (kitchen_qty = 0), Low_Level (0 < kitchen_qty <= reorder_level), and normal stock
3. THE Stock_Request_Page SHALL display Critical_Level ingredients in a visually distinct section with high priority styling
4. THE Stock_Request_Page SHALL display Low_Level ingredients in a separate section with medium priority styling
5. FOR EACH suggested Ingredient, THE Stock_Request_Page SHALL display the ingredient name, current kitchen_qty, reorder_level, unit, and available Main_Inventory quantity

### Requirement 2: Enable Quick Stock Request Creation

**User Story:** As a kitchen staff member, I want to quickly create stock requests for suggested ingredients, so that I can efficiently restock the kitchen without navigating through multiple pages.

#### Acceptance Criteria

1. FOR EACH suggested Ingredient, THE Stock_Request_Page SHALL provide a quick-action button to create a Stock_Request
2. WHEN a kitchen staff member clicks the quick-action button, THE Auto_Suggestion_System SHALL pre-populate the Stock_Request form with the Ingredient details
3. THE Auto_Suggestion_System SHALL suggest a default quantity equal to the difference between `reorder_level` and `kitchen_qty`
4. THE Stock_Request_Page SHALL allow the kitchen staff member to modify the suggested quantity before submission
5. WHEN the Stock_Request is submitted, THE Kitchen_Portal SHALL validate that the requested quantity does not exceed the available `stock_qty` in Main_Inventory

### Requirement 3: Prioritize Critical Ingredients

**User Story:** As a kitchen staff member, I want critical (out-of-stock) ingredients to be prominently displayed, so that I can prioritize restocking items that are completely depleted.

#### Acceptance Criteria

1. THE Auto_Suggestion_System SHALL sort Critical_Level ingredients to appear before Low_Level ingredients
2. THE Stock_Request_Page SHALL use a distinct visual indicator (color, icon, or badge) for Critical_Level ingredients
3. WHEN multiple Critical_Level ingredients exist, THE Auto_Suggestion_System SHALL sort them alphabetically by name
4. WHEN multiple Low_Level ingredients exist, THE Auto_Suggestion_System SHALL sort them by ascending kitchen_qty (lowest first)

### Requirement 4: Show Inventory Availability

**User Story:** As a kitchen staff member, I want to see the available quantity in Main_Inventory for each suggested ingredient, so that I know whether my stock request can be fulfilled.

#### Acceptance Criteria

1. FOR EACH suggested Ingredient, THE Stock_Request_Page SHALL display the current `stock_qty` from Main_Inventory
2. WHEN Main_Inventory `stock_qty` is 0, THE Stock_Request_Page SHALL display a warning indicator that the ingredient cannot be fulfilled
3. WHEN Main_Inventory `stock_qty` is less than the suggested request quantity, THE Stock_Request_Page SHALL display a warning that only partial fulfillment is possible
4. THE Stock_Request_Page SHALL display the unit of measurement for both kitchen_qty and stock_qty

### Requirement 5: Filter and Search Suggested Ingredients

**User Story:** As a kitchen staff member, I want to filter and search through suggested ingredients, so that I can quickly find specific items when the list is long.

#### Acceptance Criteria

1. THE Stock_Request_Page SHALL provide a search input field to filter suggested Ingredients by name
2. WHEN a kitchen staff member types in the search field, THE Auto_Suggestion_System SHALL filter the displayed Ingredients in real-time
3. THE Stock_Request_Page SHALL provide filter options to show only Critical_Level, only Low_Level, or all suggested Ingredients
4. THE Stock_Request_Page SHALL provide a category filter to show Ingredients by category (Protein, Dairy, Pantry, etc.)
5. WHEN filters are applied, THE Stock_Request_Page SHALL maintain the priority sorting within each filtered group

### Requirement 6: Refresh Auto-Suggestions

**User Story:** As a kitchen staff member, I want the auto-suggestions to update after I create a stock request, so that I see an accurate list of ingredients that still need restocking.

#### Acceptance Criteria

1. WHEN a Stock_Request is successfully created, THE Auto_Suggestion_System SHALL remove the requested Ingredient from the suggestions list if a pending request already exists
2. THE Stock_Request_Page SHALL display a badge or indicator on Ingredients that already have pending Stock_Requests
3. THE Stock_Request_Page SHALL provide a manual refresh button to reload the suggestions
4. WHEN the page is refreshed, THE Auto_Suggestion_System SHALL recalculate all suggestions based on current kitchen_qty values

### Requirement 7: Bulk Stock Request Creation

**User Story:** As a kitchen staff member, I want to select multiple suggested ingredients and create stock requests for all of them at once, so that I can save time when restocking many items.

#### Acceptance Criteria

1. THE Stock_Request_Page SHALL provide checkboxes for each suggested Ingredient
2. THE Stock_Request_Page SHALL provide a "Select All Critical" button to select all Critical_Level ingredients
3. THE Stock_Request_Page SHALL provide a "Select All Low" button to select all Low_Level ingredients
4. WHEN multiple Ingredients are selected, THE Stock_Request_Page SHALL display a bulk action button to create Stock_Requests for all selected items
5. WHEN the bulk action is triggered, THE Auto_Suggestion_System SHALL create individual Stock_Requests for each selected Ingredient with the suggested default quantities
6. WHEN bulk Stock_Requests are created, THE Kitchen_Portal SHALL validate each request against Main_Inventory availability and report any that cannot be fulfilled

### Requirement 8: Display Summary Statistics

**User Story:** As a kitchen staff member, I want to see summary statistics of ingredients needing restock, so that I can quickly understand the overall kitchen inventory status.

#### Acceptance Criteria

1. THE Stock_Request_Page SHALL display a count of Critical_Level ingredients
2. THE Stock_Request_Page SHALL display a count of Low_Level ingredients
3. THE Stock_Request_Page SHALL display the total number of pending Stock_Requests
4. THE Stock_Request_Page SHALL display the count of Ingredients with insufficient Main_Inventory to fulfill requests
