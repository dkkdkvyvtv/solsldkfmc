class VapeShop {
    constructor() {
        this.user = null;
        this.balance = 0;
        this.isAddingToCart = false;
        this.cart = {
            items: [],
            total: 0
        };
        this.deliveryType = 'pickup';
        this.selectedCity = null;
        this.selectedPickupLocation = null;
        this.deliveryPrice = 0;
        this.currentOrderStep = 'customer';
        this.init();
    }

    async init() {
        await this.initTelegramWebApp();
        this.setupEventListeners();
        this.highlightActiveNav();
        
        if (window.location.pathname === '/cart') {
            await this.loadCart();
        }
        
        if (window.location.pathname === '/profile') {
            await this.loadProfile();
        }
        
        if (window.location.pathname === '/') {
            this.updateMiniProfile();
        }
    }

    async initTelegramWebApp() {
        try {
            // ВАЖНО: Проверяем, что мы в Telegram Web App
            if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
                console.log('Telegram Web App доступен');
                const tg = window.Telegram.WebApp;
                
                // ВАЖНО: Вызываем ready() чтобы убрать "Открыть приложение"
                tg.ready();
                
                // ВАЖНО: Разворачиваем на весь экран
                tg.expand();
                
                // Получаем данные пользователя
                const tgUser = tg.initDataUnsafe?.user;
                
                if (tgUser) {
                    console.log('Данные пользователя Telegram получены');
                    
                    this.user = {
                        id: tgUser.id,
                        first_name: tgUser.first_name || 'Пользователь',
                        username: tgUser.username || `user_${tgUser.id}`,
                        photo_url: tgUser.photo_url || '/static/images/default-avatar.png'
                    };
                    
                    // Инициализируем на сервере
                    await this.initWithTelegram(tg.initData);
                    
                    // Настраиваем кнопку Telegram
                    this.setupTelegramMainButton(tg);
                    
                } else {
                    console.log('Данные пользователя Telegram не получены');
                    await this.initFallback();
                }
                
            } else {
                console.log('Не в Telegram Web App, используем браузерный режим');
                await this.initFallback();
            }
            
            this.updateMiniProfile();
            
        } catch (error) {
            console.error('Ошибка инициализации Telegram Web App:', error);
            await this.initFallback();
        }
    }

    async initWithTelegram(initData) {
        try {
            const response = await fetch('/api/init', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    initData: initData,
                    user: this.user
                })
            });
            
            const data = await response.json();
            this.balance = data.balance || 0;
            
        } catch (error) {
            console.error('Ошибка инициализации с Telegram:', error);
        }
    }

    setupTelegramMainButton(tg) {
        if (!tg || !tg.MainButton) return;
        
        // ВАЖНО: Настраиваем кнопку Telegram
        tg.MainButton.setText("Открыть каталог");
        tg.MainButton.onClick(() => {
            window.location.href = '/catalog';
        });
        
        // ВАЖНО: Показываем кнопку
        tg.MainButton.show();
        
        // Обновляем цвет фона Telegram
        tg.setBackgroundColor('#0f0f0f');
    }

    async initFallback() {
        try {
            const response = await fetch('/api/init', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            });
            
            const data = await response.json();
            this.user = data.user;
            this.balance = data.balance || 0;
            
        } catch (error) {
            console.error('Ошибка fallback инициализации:', error);
            this.user = {
                id: 1,
                first_name: 'Тестовый Пользователь',
                username: 'test_user',
                photo_url: '/static/images/default-avatar.png'
            };
            this.balance = 1500;
        }
    }

    highlightActiveNav() {
        const currentPath = window.location.pathname;
        const navItems = document.querySelectorAll('.nav-item');
        
        navItems.forEach(item => {
            item.classList.remove('active');
            const href = item.getAttribute('href');
            
            if (href === currentPath || (href === '/' && currentPath === '/')) {
                item.classList.add('active');
            }
        });
    }

    updateMiniProfile() {
        if (window.location.pathname === '/') {
            const avatar = document.getElementById('user-avatar');
            const username = document.getElementById('username');
            const balance = document.getElementById('balance');
            
            if (avatar && this.user) {
                avatar.src = this.user.photo_url || '/static/images/default-avatar.png';
                avatar.onerror = function() {
                    this.src = '/static/images/default-avatar.png';
                };
            }
            if (username && this.user) username.textContent = this.user.first_name || 'Пользователь';
            if (balance) balance.textContent = `${this.balance} руб.`;
        }
        
        if (window.location.pathname === '/profile') {
            this.updateProfilePage();
        }
    }

    updateProfilePage() {
        const avatar = document.getElementById('profile-avatar');
        const username = document.getElementById('profile-username');
        const mainBalance = document.getElementById('main-balance');
        
        if (avatar && this.user) {
            avatar.src = this.user.photo_url || '/static/images/default-avatar.png';
            avatar.onerror = function() {
                this.src = '/static/images/default-avatar.png';
            };
        }
        if (username && this.user) username.textContent = this.user.first_name || 'Пользователь';
        if (mainBalance) mainBalance.textContent = `${this.balance} руб.`;
    }

    setupEventListeners() {
        const addToCartButtons = document.querySelectorAll('.add-to-cart-btn');
        addToCartButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const productId = button.getAttribute('data-product-id');
                if (productId) {
                    this.addToCart(parseInt(productId));
                }
            });
        });
    }

    async addToCart(productId) {
        if (this.isAddingToCart) {
            return;
        }
        
        this.isAddingToCart = true;
        
        try {
            const response = await fetch('/api/cart/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_id: productId
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification('Товар добавлен в корзину');
                if (window.location.pathname === '/cart') {
                    await this.loadCart();
                }
            } else {
                this.showNotification(result.error || 'Ошибка при добавлении в корзину', 'error');
            }
        } catch (error) {
            console.error('Ошибка:', error);
            this.showNotification('Ошибка при добавлении в корзину', 'error');
        } finally {
            this.isAddingToCart = false;
        }
    }

    async loadCart() {
        try {
            const response = await fetch('/api/cart/items');
            const data = await response.json();
            this.cart = data;
            this.renderCart();
        } catch (error) {
            console.error('Ошибка загрузки корзины:', error);
            const cartItems = document.getElementById('cart-items');
            if (cartItems) {
                cartItems.innerHTML = '<div class="error">Ошибка загрузки корзины</div>';
            }
        }
    }

    renderCart() {
        const cartItems = document.getElementById('cart-items');
        const cartTotalSection = document.getElementById('cart-total-section');
        const emptyCart = document.getElementById('empty-cart');
        
        if (!this.cart.items || this.cart.items.length === 0) {
            if (cartItems) cartItems.style.display = 'none';
            if (cartTotalSection) cartTotalSection.style.display = 'none';
            if (emptyCart) emptyCart.style.display = 'block';
            return;
        }
        
        if (emptyCart) emptyCart.style.display = 'none';
        if (cartTotalSection) cartTotalSection.style.display = 'block';
        if (cartItems) {
            cartItems.style.display = 'block';
            cartItems.innerHTML = this.cart.items.map(item => `
                <div class="cart-item">
                    <div class="cart-item-image">
                        <img src="${item.image}" alt="${item.name}" onerror="this.src='/static/images/default-product.png'">
                    </div>
                    <div class="cart-item-info">
                        <h4>${item.name}</h4>
                        <div class="item-price">${item.price || 0} руб. × ${item.quantity || 1}</div>
                        <div class="quantity-controls">
                            <button class="quantity-btn" onclick="vapeShop.updateQuantity(${item.id}, ${(item.quantity || 1) - 1})">-</button>
                            <span>${item.quantity || 1}</span>
                            <button class="quantity-btn" onclick="vapeShop.updateQuantity(${item.id}, ${(item.quantity || 1) + 1})">+</button>
                        </div>
                    </div>
                    <div class="item-total">${(item.total || 0)} руб.</div>
                </div>
            `).join('');
        }
        
        if (document.getElementById('cart-total')) {
            document.getElementById('cart-total').textContent = (this.cart.total || 0) + ' руб.';
        }
        if (document.getElementById('cashback-amount')) {
            document.getElementById('cashback-amount').textContent = ((this.cart.total || 0) * 0.03).toFixed(2) + ' руб.';
        }
        if (document.getElementById('order-total-amount')) {
            document.getElementById('order-total-amount').textContent = (this.cart.total || 0) + ' руб.';
        }
    }

    async updateQuantity(productId, newQuantity) {
        if (newQuantity < 1) {
            await this.removeFromCart(productId);
            return;
        }
        
        try {
            const response = await fetch('/api/cart/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_id: productId,
                    quantity: newQuantity
                })
            });
            
            const result = await response.json();
            if (result.success) {
                await this.loadCart();
                this.updateOrderSummary();
            }
        } catch (error) {
            console.error('Ошибка обновления количества:', error);
            this.showNotification('Ошибка обновления количества', 'error');
        }
    }

    async removeFromCart(productId) {
        try {
            const response = await fetch('/api/cart/remove', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    product_id: productId
                })
            });
            
            const result = await response.json();
            if (result.success) {
                await this.loadCart();
                this.updateOrderSummary();
            }
        } catch (error) {
            console.error('Ошибка удаления из корзины:', error);
            this.showNotification('Ошибка удаления из корзины', 'error');
        }
    }

    async loadProfile() {
        try {
            const response = await fetch('/api/user/profile');
            const data = await response.json();
            this.renderProfile(data);
        } catch (error) {
            console.error('Ошибка загрузки профиля:', error);
        }
    }

    renderProfile(data) {
        this.balance = data.balance || 0;
        this.updateProfilePage();
        
        this.renderOrders(data.orders || []);
    }

    renderOrders(orders) {
        const ordersList = document.getElementById('orders-list');
        if (!ordersList) return;
        
        if (orders.length === 0) {
            ordersList.innerHTML = `
                <div class="empty-orders">
                    <div class="empty-icon">📦</div>
                    <h4>Заказов пока нет</h4>
                    <p>Сделайте свой первый заказ!</p>
                </div>
            `;
            return;
        }
        
        ordersList.innerHTML = orders.map(order => {
            let statusText = '';
            let statusClass = '';
            
            switch(order.status) {
                case 'completed':
                    statusText = 'Выполнен';
                    statusClass = 'status-completed';
                    break;
                case 'pending':
                    statusText = 'В обработке';
                    statusClass = 'status-pending';
                    break;
                case 'cancelled':
                    statusText = 'Отменен';
                    statusClass = 'status-cancelled';
                    break;
                default:
                    statusText = order.status;
                    statusClass = 'status-pending';
            }
            
            const orderDate = new Date(order.created_at);
            const formattedDate = orderDate.toLocaleDateString('ru-RU', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
            
            let deliveryInfo = '';
            if (order.delivery_type === 'pickup') {
                deliveryInfo = order.pickup_location || 'Пункт выдачи не указан';
            } else {
                deliveryInfo = order.delivery_city ? `Доставка в ${order.delivery_city}` : 'Доставка';
            }
            
            return `
                <div class="order-item">
                    <div class="order-header">
                        <div class="order-id">Заказ #${order.id}</div>
                        <div class="order-date">${formattedDate}</div>
                    </div>
                    <div class="order-details">
                        <div>
                            <span>Сумма:</span>
                            <span>${order.total_amount} руб.</span>
                        </div>
                        <div>
                            <span>Кешбек:</span>
                            <span>+${order.cashback_earned} руб.</span>
                        </div>
                        <div>
                            <span>Получение:</span>
                            <span>${deliveryInfo}</span>
                        </div>
                        <div>
                            <span>Статус:</span>
                            <span class="order-status ${statusClass}">${statusText}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    async openOrderModal() {
        const modal = document.getElementById('order-modal');
        if (modal) {
            modal.style.display = 'flex';
            
            this.deliveryType = 'pickup';
            this.selectedCity = null;
            this.selectedPickupLocation = null;
            this.deliveryPrice = 0;
            this.currentOrderStep = 'customer';
            
            this.showOrderStep('customer');
            
            await this.loadCities();
            
            this.updateOrderSummary();
        }
    }

    async loadCities() {
        try {
            const response = await fetch('/api/cities');
            const cities = await response.json();
            
            const citySelector = document.getElementById('city-selector');
            if (citySelector) {
                if (cities.length === 0) {
                    citySelector.innerHTML = '<div class="loading-cities">Нет доступных городов</div>';
                    return;
                }
                
                citySelector.innerHTML = cities.map(city => `
                    <button type="button" class="city-btn" onclick="vapeShop.selectCity('${city}')">
                        ${city}
                    </button>
                `).join('');
            }
        } catch (error) {
            console.error('Ошибка загрузки городов:', error);
        }
    }

    async loadPickupLocations() {
        if (!this.selectedCity) return;
        
        try {
            const response = await fetch(`/api/pickup-locations?type=pickup&city=${encodeURIComponent(this.selectedCity)}`);
            const locations = await response.json();
            
            const pickupLocationSelect = document.getElementById('pickup-location');
            if (pickupLocationSelect) {
                pickupLocationSelect.innerHTML = '<option value="">Выберите пункт выдачи</option>';
                
                if (locations.length === 0) {
                    pickupLocationSelect.innerHTML += '<option value="" disabled>Нет доступных пунктов</option>';
                    pickupLocationSelect.disabled = true;
                } else {
                    locations.forEach(loc => {
                        pickupLocationSelect.innerHTML += `<option value="${loc.id}">${loc.name} - ${loc.address}</option>`;
                    });
                    pickupLocationSelect.disabled = false;
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки пунктов выдачи:', error);
        }
    }

    async loadDeliveryPrice() {
        if (!this.selectedCity || this.deliveryType !== 'delivery') return;
        
        try {
            const response = await fetch(`/api/pickup-locations?type=delivery&city=${encodeURIComponent(this.selectedCity)}`);
            const locations = await response.json();
            
            if (locations.length > 0) {
                this.deliveryPrice = locations[0].delivery_price || 0;
                const deliveryPriceElement = document.getElementById('delivery-price-amount');
                if (deliveryPriceElement) {
                    deliveryPriceElement.textContent = this.deliveryPrice;
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки стоимости доставки:', error);
        }
    }

    selectCity(city) {
        this.selectedCity = city;
        
        const cityButtons = document.querySelectorAll('.city-btn');
        cityButtons.forEach(btn => {
            if (btn.textContent === city) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        
        const cityInfo = document.getElementById('city-info');
        const selectedCityName = document.getElementById('selected-city-name');
        if (cityInfo && selectedCityName) {
            selectedCityName.textContent = city;
            cityInfo.style.display = 'block';
        }
        
        this.updateNextCityButton();
        
        this.updateOrderSummary();
    }

    updateNextCityButton() {
        const nextBtn = document.getElementById('next-city-btn');
        if (nextBtn) {
            nextBtn.disabled = !this.selectedCity;
        }
    }

    showOrderStep(stepId) {
        document.querySelectorAll('.order-step').forEach(step => {
            step.style.display = 'none';
            step.classList.remove('active');
        });
        
        const step = document.getElementById(`step-${stepId}`);
        if (step) {
            step.style.display = 'block';
            step.classList.add('active');
            this.currentOrderStep = stepId;
        }
    }

    nextOrderStep(nextStepId) {
        if (!this.validateCurrentStep()) {
            return;
        }
        
        this.updateOrderSummary();
        
        this.showOrderStep(nextStepId);
        
        if (nextStepId === 'city') {
            this.updateNextCityButton();
        }
        
        if (nextStepId === 'location') {
            if (this.deliveryType === 'pickup') {
                this.loadPickupLocations();
            }
            this.updateDeliveryInfo();
        }
    }

    prevOrderStep(prevStepId) {
        this.showOrderStep(prevStepId);
    }

    validateCurrentStep() {
        switch(this.currentOrderStep) {
            case 'customer':
                const name = document.getElementById('customer-name');
                const phone = document.getElementById('customer-phone');
                
                if (!name || !phone) return true;
                
                if (!name.value.trim()) {
                    this.showErrorNotification('Введите ваше имя', 'customer-name');
                    return false;
                }
                if (!phone.value.trim()) {
                    this.showErrorNotification('Введите номер телефона', 'customer-phone');
                    return false;
                }
                return true;
                
            case 'city':
                if (!this.selectedCity) {
                    this.showErrorNotification('Выберите город');
                    return false;
                }
                return true;
                
            case 'location':
                if (this.deliveryType === 'pickup') {
                    const pickupLocation = document.getElementById('pickup-location');
                    if (!pickupLocation || !pickupLocation.value) {
                        this.showErrorNotification('Выберите пункт выдачи', 'pickup-location');
                        return false;
                    }
                } else {
                    const deliveryAddress = document.getElementById('delivery-address');
                    if (!deliveryAddress || !deliveryAddress.value.trim()) {
                        this.showErrorNotification('Введите адрес доставки', 'delivery-address');
                        return false;
                    }
                }
                return true;
        }
        return true;
    }

    showErrorNotification(message, fieldId = null) {
        this.showNotification(message, 'error');
        
        if (fieldId) {
            const field = document.getElementById(fieldId);
            if (field) {
                field.style.borderColor = '#ff4444';
                setTimeout(() => {
                    field.style.borderColor = '';
                }, 2000);
            }
        }
    }

    setDeliveryType(type) {
        this.deliveryType = type;
        
        const deliveryButtons = document.querySelectorAll('.delivery-type-btn');
        deliveryButtons.forEach(btn => {
            if (btn.dataset.type === type) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        
        const pickupSection = document.getElementById('pickup-section');
        const deliverySection = document.getElementById('delivery-section');
        
        if (pickupSection) pickupSection.style.display = type === 'pickup' ? 'block' : 'none';
        if (deliverySection) deliverySection.style.display = type === 'delivery' ? 'block' : 'none';
        
        this.updateDeliveryInfo();
    }

    updateDeliveryInfo() {
        if (this.deliveryType === 'delivery' && this.selectedCity) {
            this.loadDeliveryPrice();
        } else {
            this.deliveryPrice = 0;
        }
        this.updateOrderSummary();
    }

    updateOrderSummary() {
        const orderItemsList = document.getElementById('order-items-list');
        const orderSubtotal = document.getElementById('order-subtotal');
        const deliveryFeeRow = document.getElementById('delivery-fee-row');
        const deliveryFee = document.getElementById('delivery-fee');
        const finalTotal = document.getElementById('final-total');
        const summaryCashback = document.getElementById('summary-cashback');
        
        if (!orderItemsList || !orderSubtotal) return;
        
        let itemsHtml = '';
        let subtotal = 0;
        
        this.cart.items.forEach(item => {
            const itemTotal = item.price * item.quantity;
            subtotal += itemTotal;
            itemsHtml += `
                <div class="order-item">
                    <span>${item.name} × ${item.quantity}</span>
                    <span>${itemTotal} руб.</span>
                </div>
            `;
        });
        
        orderItemsList.innerHTML = itemsHtml;
        orderSubtotal.textContent = subtotal + ' руб.';
        
        const total = subtotal + this.deliveryPrice;
        if (this.deliveryPrice > 0) {
            if (deliveryFeeRow) deliveryFeeRow.style.display = 'flex';
            if (deliveryFee) deliveryFee.textContent = this.deliveryPrice + ' руб.';
        } else {
            if (deliveryFeeRow) deliveryFeeRow.style.display = 'none';
        }
        
        if (finalTotal) {
            finalTotal.textContent = total + ' руб.';
        }
        
        const cashback = total * 0.03;
        if (summaryCashback) {
            summaryCashback.textContent = cashback.toFixed(2) + ' руб.';
        }
        
        this.updateOrderDetailsSummary();
    }

    updateOrderDetailsSummary() {
        const name = document.getElementById('customer-name');
        const phone = document.getElementById('customer-phone');
        
        if (name && name.value) {
            const summaryName = document.getElementById('summary-name');
            if (summaryName) summaryName.textContent = name.value;
        }
        
        if (phone && phone.value) {
            const summaryPhone = document.getElementById('summary-phone');
            if (summaryPhone) summaryPhone.textContent = phone.value;
        }
        
        const deliveryTypeText = this.deliveryType === 'pickup' ? 'Самовывоз' : 'Доставка';
        const summaryDeliveryType = document.getElementById('summary-delivery-type');
        if (summaryDeliveryType) summaryDeliveryType.textContent = deliveryTypeText;
        
        const summaryCity = document.getElementById('summary-city');
        if (summaryCity) summaryCity.textContent = this.selectedCity || '-';
        
        if (this.deliveryType === 'pickup') {
            const summaryPickupItem = document.getElementById('summary-pickup-item');
            const summaryAddressItem = document.getElementById('summary-address-item');
            if (summaryPickupItem) summaryPickupItem.style.display = 'flex';
            if (summaryAddressItem) summaryAddressItem.style.display = 'none';
            
            const pickupSelect = document.getElementById('pickup-location');
            const summaryPickup = document.getElementById('summary-pickup');
            if (pickupSelect && pickupSelect.value && summaryPickup) {
                const selectedOption = pickupSelect.options[pickupSelect.selectedIndex];
                summaryPickup.textContent = selectedOption.text || '-';
            } else if (summaryPickup) {
                summaryPickup.textContent = '-';
            }
        } else {
            const summaryPickupItem = document.getElementById('summary-pickup-item');
            const summaryAddressItem = document.getElementById('summary-address-item');
            if (summaryPickupItem) summaryPickupItem.style.display = 'none';
            if (summaryAddressItem) summaryAddressItem.style.display = 'flex';
            
            const address = document.getElementById('delivery-address');
            const summaryAddress = document.getElementById('summary-address');
            if (address && address.value && summaryAddress) {
                summaryAddress.textContent = address.value || '-';
            } else if (summaryAddress) {
                summaryAddress.textContent = '-';
            }
        }
    }

    async submitOrder(e) {
        if (e) e.preventDefault();
        
        if (!this.validateCurrentStep()) {
            return;
        }
        
        const customerName = document.getElementById('customer-name');
        const customerPhone = document.getElementById('customer-phone');
        const pickupLocationSelect = document.getElementById('pickup-location');
        const deliveryAddress = document.getElementById('delivery-address');
        
        if (!customerName || !customerPhone) return;
        
        const formData = {
            customer_name: customerName.value,
            customer_phone: customerPhone.value,
            delivery_type: this.deliveryType,
            delivery_city: this.selectedCity
        };
        
        if (this.deliveryType === 'pickup') {
            if (!pickupLocationSelect || !pickupLocationSelect.value) {
                this.showErrorNotification('Выберите пункт выдачи');
                return;
            }
            formData.pickup_location_id = pickupLocationSelect.value;
        } else if (this.deliveryType === 'delivery') {
            if (!deliveryAddress || !deliveryAddress.value.trim()) {
                this.showErrorNotification('Введите адрес доставки');
                return;
            }
            formData.delivery_address = deliveryAddress.value.trim();
        }
        
        if (!formData.customer_name || !formData.customer_phone || !formData.delivery_city) {
            this.showErrorNotification('Заполните все обязательные поля');
            return;
        }
        
        try {
            const response = await fetch('/api/order/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showNotification(result.message || 'Заказ успешно оформлен');
                this.closeModal();
                setTimeout(() => {
                    window.location.href = '/profile';
                }, 2000);
            } else {
                this.showErrorNotification(result.error || 'Ошибка оформления заказа');
            }
        } catch (error) {
            console.error('Ошибка:', error);
            this.showErrorNotification('Ошибка оформления заказа');
        }
    }

    closeModal() {
        const modal = document.getElementById('order-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    showNotification(message, type = 'success') {
        const existingNotifications = document.querySelectorAll('.notification');
        existingNotifications.forEach(notification => notification.remove());
        
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#00ff88' : '#ff4444'};
            color: ${type === 'success' ? '#000' : '#fff'};
            padding: 15px 25px;
            border-radius: 10px;
            z-index: 10000;
            font-weight: bold;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
            transform: translateX(400px);
            transition: transform 0.3s ease-in-out;
            max-width: 300px;
            word-wrap: break-word;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.transform = 'translateX(0)';
        }, 100);
        
        setTimeout(() => {
            notification.style.transform = 'translateX(400px)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
}

const vapeShop = new VapeShop();

// Глобальные функции для использования в HTML
function addToCart(productId) {
    vapeShop.addToCart(productId);
}

function updateQuantity(productId, quantity) {
    vapeShop.updateQuantity(productId, quantity);
}

function openOrderModal() {
    vapeShop.openOrderModal();
}

function closeModal() {
    vapeShop.closeModal();
}

function selectCity(city) {
    vapeShop.selectCity(city);
}

function setDeliveryType(type) {
    vapeShop.setDeliveryType(type);
}

function showOrderStep(stepId) {
    vapeShop.showOrderStep(stepId);
}

function nextOrderStep(nextStepId) {
    vapeShop.nextOrderStep(nextStepId);
}

function prevOrderStep(prevStepId) {
    vapeShop.prevOrderStep(prevStepId);
}