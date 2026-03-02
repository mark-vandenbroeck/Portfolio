/**
 * table_utils.js
 * 
 * Provides generic sorting and filtering capabilities for tables with the 'modern-table' class.
 * Ensures consistent arrow indicators and data parsing (dates, currencies, percentages, numbers).
 */

document.addEventListener('DOMContentLoaded', () => {
    // Make all modern-tables sortable by clicking headers
    document.querySelectorAll('.modern-table').forEach(table => {
        const headers = table.querySelectorAll('th');

        headers.forEach((header, index) => {
            // Check if column is sortable (we skip empty headers like action columns)
            if (header.innerText.trim() !== '') {
                header.style.cursor = 'pointer';
                header.classList.add('sortable-header');
                // Set initial icon explicitly
                let icon = document.createElement('span');
                icon.className = 'sort-icon';
                icon.innerHTML = ' &#9650;&#9660;'; // Up/Down arrows
                icon.style.opacity = '0.3';
                icon.style.fontSize = '0.7em';
                icon.style.marginLeft = '5px';
                header.appendChild(icon);

                let sortAsc = true;
                header.addEventListener('click', () => {
                    // Reset all other headers in this table
                    headers.forEach(h => {
                        const i = h.querySelector('.sort-icon');
                        if (i) i.style.opacity = '0.3';
                    });

                    // Set active header
                    const activeIcon = header.querySelector('.sort-icon');
                    if (activeIcon) activeIcon.style.opacity = '1.0';
                    if (activeIcon) activeIcon.innerHTML = sortAsc ? ' &#9650;' : ' &#9660;';

                    sortTable(table, index, sortAsc);
                    sortAsc = !sortAsc;
                });
            }
        });
    });
});

/**
 * Sorts an HTML table depending on the content of the clicked column.
 */
function sortTable(table, colIndex, asc) {
    const tbody = table.querySelector('tbody');
    // We only sort rows inside tbody, ignoring totals/tfoot
    const rowsList = Array.from(tbody.querySelectorAll('tr'));

    // Ignore empty states
    if (rowsList.length === 0 || rowsList[0].querySelector('.empty-state')) return;

    rowsList.sort((rowA, rowB) => {
        let cellA = rowA.children[colIndex].textContent.trim();
        let cellB = rowB.children[colIndex].textContent.trim();

        // Data cleanup for parsing
        const valA = parseCellValue(cellA);
        const valB = parseCellValue(cellB);

        // Compare logic
        if (valA < valB) return asc ? -1 : 1;
        if (valA > valB) return asc ? 1 : -1;
        return 0;
    });

    // Re-append rows in sorted order
    rowsList.forEach(row => tbody.appendChild(row));
}

/**
 * Parses generic table string values into sortable formats (Numbers, Dates, or lowercase strings).
 */
function parseCellValue(str) {
    if (!str || str === '-') return -Infinity; // Put empty/dashes at the bottom

    // Check Date format (YYYY-MM-DD HH:MM:SS)
    if (/^\d{4}-\d{2}-\d{2}/.test(str)) {
        const d = new Date(str);
        if (!isNaN(d)) return d.getTime();
    }

    // Check Currency (remove € symbol, commas to dots for JS parsing)
    // E.g. "€ 1,234.56" or "1.234,56"
    // Because formatLocal in JS might use dots for thousands and commas for decimals in NL
    // or vice versa depending on rendering script. In backend we use Jinja "%.2f" which uses dots.
    let cleanStr = str.replace(/[€%\s]/g, '');
    let numVal = parseFloat(cleanStr);

    if (!isNaN(numVal) && cleanStr.match(/^[\d.-]+$/)) {
        return numVal;
    }

    // Default to case-insensitive string compare
    return str.toLowerCase();
}
