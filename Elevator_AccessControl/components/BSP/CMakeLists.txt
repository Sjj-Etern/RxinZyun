set(src_dirs
            EMISSION
            IIC
            LCD
            LED
            SPI
            DHT11
            RELAY
            WIFI
            XL9555)

set(include_dirs
            EMISSION
            IIC
            LCD
            LED
            SPI
            DHT11
            RELAY
            WIFI
            XL9555)

set(requires
            esp_wifi
            esp_http_client
            cjson nvs_flash
            driver)

idf_component_register(SRC_DIRS ${src_dirs} INCLUDE_DIRS ${include_dirs} REQUIRES ${requires})

component_compile_options(-ffast-math -O3 -Wno-error=format=-Wno-format)